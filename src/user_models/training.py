"""Training service — wraps OnlineEnvTrainer, runs as an asyncio task."""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


async def run_training_service(state: Any):
    """Main training coroutine — lazy-initializes the trainer and runs the streaming loop.

    In prompted mode, initializes the predictor and returns immediately.
    """
    

    config = state.config
    loop = asyncio.get_running_loop()

    # ── DataManager init (shared by all model types) ───────────────────────────
    if state.model.data_manager is None:
        from user_models.data_manager import DataManager
        dm = DataManager(log_dir=config.log_dir)
        await dm.start()
        state.model.data_manager = dm
        logger.info("DataManager started")

    # ── Trainer init (powernap mode only) ─────────────────────────────────────
    if config.model_type == "powernap":
        if state.model.trainer is None:
            logger.info("Initializing trainer (first start)...")
            from user_models.powernap.longnap.trainer import OnlineEnvTrainer

            def _init_trainer():
                return OnlineEnvTrainer(
                    data_manager=state.model.data_manager,
                    model_name=config.model,
                    reward_llm=config.reward_llm,
                    reward_llm_api_key=config.reward_llm_api_key or config.default_llm_api_key,
                    num_generations=config.num_generations,
                    learning_rate=config.learning_rate,
                    max_tokens=config.max_completion_length,
                    num_imgs_per_sample=config.num_imgs_per_sample,
                    log_dir=config.log_dir,
                    log_to_wandb=config.log_to_wandb,
                    wandb_project=config.wandb_project,
                    wandb_run_name=config.wandb_run_name,
                    checkpoint_every_n_steps=config.checkpoint_every_n_steps,
                    resume_from_checkpoint=config.resume_from_checkpoint,
                    retriever_checkpoint=config.retriever_checkpoint,
                    sampler_ttl_seconds=config.sampler_ttl_seconds or None,
                    loss_mode=config.loss_mode,
                    eval_with_llm_judge=config.eval_with_llm_judge,
                )

            state.model.trainer = await loop.run_in_executor(None, _init_trainer)
            logger.info("Trainer initialized")

            try:
                import wandb
                if wandb.run is not None:
                    wandb_url = wandb.run.get_url()
                    logger.info(f"WandB run: {wandb_url}")
                    await state.broadcast("wandb_url", {"url": wandb_url})
            except Exception:
                pass

        else:
            logger.info("Refreshing sampler for existing trainer...")
            await loop.run_in_executor(None, state.model.trainer.refresh_sampler)

    # ── Predictor init ────────────────────────────────────────────────────────
    if state.model.predictor is None:
        if config.model_type == "powernap":
            from user_models.powernap.inference import FinetunedPredictor

            def _init_predictor():
                return FinetunedPredictor(
                    data_manager=state.model.data_manager,
                    renderer=state.model.trainer.renderer,
                    tokenizer=state.model.trainer.tokenizer,
                    max_tokens=config.max_completion_length,
                    retriever=state.model.trainer.retriever,
                    log_dir=config.log_dir,
                    sampling_client=state.model.trainer.sampling_client,
                )

            state.model.predictor = await loop.run_in_executor(None, _init_predictor)

        elif config.model_type == "prompted":
            from user_models.prompted import PromptedPredictor

            def _init_prompted():
                return PromptedPredictor(
                    data_manager=state.model.data_manager,
                    model=config.prompted_model,
                    api_key=config.default_llm_api_key,
                    max_tokens=config.max_completion_length,
                    log_dir=config.log_dir,
                )

            state.model.predictor = await loop.run_in_executor(None, _init_prompted)
            logger.info(f"Prompted predictor initialized (model={config.prompted_model})")

    # ── Prompted mode: watch for label updates, no training loop ──────────────
    if config.model_type != "powernap":
        logger.info("Prompted mode: watching for label updates")
        while True:
            try:
                await asyncio.wait_for(data_manager.wait_for_label(), timeout=5.0)
                screen = state.connectors.get("screen")
                await state.broadcast("status", {
                    "recording_active": screen is not None and not screen.paused,
                    "training_active": False,
                    "inference_active": state.model.inference_active,
                    "labels_processed": data_manager.labels_processed,
                })
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("Prompted label watcher cancelled")
                break
        return

    # ── Powernap training loop ─────────────────────────────────────────────────
    trainer = state.model.trainer
    data_manager = state.model.data_manager
    past_len = config.past_len
    future_len = config.future_len
    batch_size = config.batch_size
    num_imgs_per_sample = config.num_imgs_per_sample

    from user_models.powernap.longnap.trainer import make_sample

    min_required = past_len + future_len

    while True:
        try:
            if not state.model.training_active:
                await state.model.training_resumed.wait()
                continue

            try:
                await asyncio.wait_for(data_manager.wait_for_label(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            predict_count = sum(1 for e in data_manager.buffer if e.get("prediction_event"))
            logger.info(f"Training buffer: {predict_count}/{min_required} prediction events")
            screen = state.connectors.get("screen")
            await state.broadcast("status", {
                "recording_active": screen is not None and not screen.paused,
                "training_active": state.model.training_active,
                "inference_active": state.model.inference_active,
                "labels_processed": data_manager.labels_processed,
            })

            if predict_count < min_required:
                continue

            step_start = time.time()

            rollout_tasks = [
                asyncio.create_task(trainer._rollout_one_sample(
                    make_sample(data_manager.buffer, past_len, future_len, num_imgs_per_sample)
                ))
                for _ in range(batch_size)
            ]

            results = await asyncio.gather(*rollout_tasks, return_exceptions=True)

            traj_groups = []
            samples_for_batch = []
            builders_for_batch = []
            for traj_group, sample_r, builder in results:
                traj_groups.append(traj_group)
                samples_for_batch.append(sample_r)
                builders_for_batch.append(builder)

            if config.loss_mode == "logprob_elbo":
                fwdbwd_future, extra_metrics = trainer._train_batch_elbo(
                    traj_groups, samples_for_batch, builders_for_batch
                )
            else:
                fwdbwd_future, extra_metrics = trainer._train_batch_llm_judge(
                    traj_groups, samples_for_batch, builders_for_batch
                )

            fwdbwd_futures = [fwdbwd_future] if fwdbwd_future is not None else []
            extra_metrics_list = [extra_metrics] if extra_metrics else []

            if fwdbwd_futures:
                metrics = await trainer._finish_step(
                    fwdbwd_futures, traj_groups, step_start,
                    extra_metrics_list, samples_for_batch,
                    builders=builders_for_batch,
                )

                if state.model.predictor is not None:
                    state.model.predictor.sampling_client = trainer.sampling_client

                step_payload = {
                    "step": trainer._step,
                    "loss": metrics.get("train/loss", 0),
                    "reward_mean": metrics.get("train/reward_mean", 0),
                    "accuracy_mean": metrics.get("train/accuracy_mean", 0),
                    "formatting_mean": metrics.get("train/formatting_mean", 0),
                }
                await state.broadcast("training_step", step_payload)

                metrics_path = Path(config.log_dir) / "metrics.jsonl"
                with open(metrics_path, "a") as f:
                    f.write(json.dumps(step_payload) + "\n")

                if "train/logprob_reward_mean" in metrics:
                    await state.broadcast("elbo_score", {
                        "logprob_reward_mean": metrics["train/logprob_reward_mean"],
                        "logprob_reward_std": metrics.get("train/logprob_reward_std", 0),
                    })

        except asyncio.CancelledError:
            logger.info("Training service cancelled")
            break
        except Exception as e:
            logger.error(f"Training step failed: {e}", exc_info=True)

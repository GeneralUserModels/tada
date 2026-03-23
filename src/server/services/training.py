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

    Reads from state.label_queue (populated by the labeling service), constructs
    samples, runs rollouts + forward_backward + optim_step, and broadcasts metrics.
    """
    from server.ws.handler import broadcast

    config = state.config

    # Lazy-init trainer (run in thread pool — tinker client init is sync-only)
    loop = asyncio.get_running_loop()
    if state.trainer is None:
        logger.info("Initializing trainer (first start)...")
        from powernap.longnap.trainer import OnlineEnvTrainer

        def _init_trainer():
            return OnlineEnvTrainer(
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

        state.trainer = await loop.run_in_executor(None, _init_trainer)
        logger.info("Trainer initialized")

        # Broadcast wandb URL if logging is enabled
        try:
            import wandb
            if wandb.run is not None:
                wandb_url = wandb.run.get_url()
                logger.info(f"WandB run: {wandb_url}")
                await broadcast(state, "wandb_url", {"url": wandb_url})
        except Exception:
            pass

    else:
        # Trainer already exists — refresh sampler (TTL may have expired while stopped)
        logger.info("Refreshing sampler for existing trainer...")
        await loop.run_in_executor(None, state.trainer.refresh_sampler)

    # Lazy-init predictor (shares components with trainer)
    if state.predictor is None:
        from powernap.inference import Predictor

        def _init_predictor():
            return Predictor(
                renderer=state.trainer.renderer,
                tokenizer=state.trainer.tokenizer,
                max_tokens=config.max_completion_length,
                retriever=state.trainer.retriever,
                log_dir=config.log_dir,
            )

        state.predictor = await loop.run_in_executor(None, _init_predictor)

    trainer = state.trainer
    label_queue = state.label_queue
    past_len = config.past_len
    future_len = config.future_len
    batch_size = config.batch_size
    num_imgs_per_sample = config.num_imgs_per_sample

    from powernap.longnap.trainer import make_sample

    min_required = past_len + future_len

    while True:
        try:
            # When paused: idle
            if not state.training_active:
                await state.training_resumed.wait()
                continue

            # Wait for a new screen label (used as trigger only)
            try:
                item = await asyncio.wait_for(label_queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue

            if item is None:
                continue  # ignore stale sentinels

            state.untrained_batches = label_queue.qsize()
            predict_count = sum(1 for e in state.context_buffer if e.get("prediction_event"))
            logger.info(f"Training buffer: {predict_count}/{min_required} prediction events")
            await broadcast(state, "status", {
                "recording_active": state.recording_active,
                "training_active": state.training_active,
                "inference_active": state.inference_active,
                "untrained_batches": state.untrained_batches,
                "labels_processed": state.labels_processed,
                "context_buffer_size": len(state.context_buffer),
            })

            if predict_count < min_required:
                continue

            # Build sample and run one training step
            step_start = time.time()
            sample = make_sample(state.context_buffer, past_len, future_len, num_imgs_per_sample)

            # Run batch_size rollouts concurrently
            rollout_tasks = []
            for i in range(batch_size):
                if predict_count >= min_required:
                    s = make_sample(state.context_buffer, past_len, future_len, num_imgs_per_sample)
                    rollout_tasks.append(asyncio.create_task(trainer._rollout_one_sample(s)))

            if not rollout_tasks:
                continue

            results = await asyncio.gather(*rollout_tasks, return_exceptions=True)

            traj_groups = []
            samples_for_batch = []
            builders_for_batch = []
            for traj_group, sample_r, builder in results:
                traj_groups.append(traj_group)
                samples_for_batch.append(sample_r)
                builders_for_batch.append(builder)

            # Batched training
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

                state.step_count = trainer._step

                # Broadcast training step
                step_payload = {
                    "step": trainer._step,
                    "loss": metrics.get("train/loss", 0),
                    "reward_mean": metrics.get("train/reward_mean", 0),
                    "accuracy_mean": metrics.get("train/accuracy_mean", 0),
                    "formatting_mean": metrics.get("train/formatting_mean", 0),
                }
                await broadcast(state, "training_step", step_payload)

                # Persist metrics to disk
                metrics_path = Path(config.log_dir) / "metrics.jsonl"
                with open(metrics_path, "a") as f:
                    f.write(json.dumps(step_payload) + "\n")

                # Broadcast ELBO scores if applicable
                if "train/logprob_reward_mean" in metrics:
                    await broadcast(state, "elbo_score", {
                        "logprob_reward_mean": metrics["train/logprob_reward_mean"],
                        "logprob_reward_std": metrics.get("train/logprob_reward_std", 0),
                    })

            # Trim buffer
            if len(state.context_buffer) > min_required:
                state.context_buffer = state.context_buffer[-min_required:]

        except asyncio.CancelledError:
            logger.info("Training service cancelled")
            break
        except Exception as e:
            logger.error(f"Training step failed: {e}", exc_info=True)

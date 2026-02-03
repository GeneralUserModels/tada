"""
ELBO training for offline LongNAP.

Implements the 2-stage SFT -> RL ELBO training loop:
1. SFT forward_backward with GT tokens to get logprob rewards
2. RL forward_backward on CoT tokens with logprob-derived advantages

Mirrors the online trainer's _train_batch_elbo (trainer.py:390-486) but as
standalone async functions suitable for the offline training script.
"""

import logging
import os
import time
from typing import Any

import tinker
import torch

from tinker_cookbook import checkpoint_utils
from tinker_cookbook.rl import train
from tinker_cookbook.rl.data_processing import trajectory_to_data
from tinker_cookbook.rl.train import (
    _remove_mask,
    gather_with_progress,
    do_group_rollout_and_filter_constant_reward,
    print_group,
    run_evaluations_parallel,
    save_checkpoint_and_get_sampling_client,
    _get_logtree_scope,
)
from tinker_cookbook.rl.types import Trajectory, TrajectoryGroup
from tinker_cookbook.supervised.common import datum_from_model_input_weights
from tinker_cookbook.utils import ml_log

logger = logging.getLogger(__name__)


async def elbo_train_step(
    training_client: tinker.TrainingClient,
    tokenizer,
    traj_groups: list[TrajectoryGroup],
    builders: list,
    eval_with_llm_judge: bool = False,
) -> tuple[Any, dict[str, float]]:
    """ELBO training step: SFT forward_backward (blocking) then RL forward_backward.

    Args:
        training_client: Tinker training client.
        tokenizer: Tokenizer for encoding ground truth tokens.
        traj_groups: Trajectory groups from rollouts.
        builders: LongNAPEnvGroupBuilder instances (must have .input_data["solution"]).
        eval_with_llm_judge: If True, also log LLM judge reward from rollouts.

    Returns:
        (rl_fwdbwd_future_or_None, metrics_dict)
    """
    # --- Build ALL SFT datums across all groups ---
    all_sft_data = []
    group_info = []  # (num_trajs, num_gt_tokens) per group
    for traj_group, builder in zip(traj_groups, builders):
        gt_tokens = tokenizer.encode(builder.input_data["solution"], add_special_tokens=False)
        num_trajs = len(traj_group.trajectories_G)
        group_info.append((num_trajs, len(gt_tokens)))
        for traj in traj_group.trajectories_G:
            actions_ob = traj.transitions[2].ob
            full_chunks = list(actions_ob.chunks) + [tinker.EncodedTextChunk(tokens=gt_tokens)]
            prompt_len = actions_ob.length
            weights = torch.zeros(prompt_len + len(gt_tokens))
            weights[prompt_len:] = 1.0
            sft_datum = datum_from_model_input_weights(
                tinker.ModelInput(chunks=full_chunks), weights
            )
            all_sft_data.append(sft_datum)

    if not all_sft_data:
        return None, {}

    # --- SFT forward_backward — BLOCKING (need logprobs for reward) ---
    logger.info(f"ELBO: SFT forward_backward on {len(all_sft_data)} datums")
    sft_future = await training_client.forward_backward_async(
        all_sft_data, loss_fn="cross_entropy",
    )
    sft_result = await sft_future.result_async()

    # --- Extract rewards per trajectory, GRPO normalize per group ---
    all_rl_data = []
    datum_idx = 0
    total_gt_tokens = 0
    all_logprob_rewards = []

    for traj_group, builder in zip(traj_groups, builders):
        gt_tokens = tokenizer.encode(builder.input_data["solution"], add_special_tokens=False)
        num_trajs = len(traj_group.trajectories_G)
        rewards = []
        for _i in range(num_trajs):
            logprobs = sft_result.loss_fn_outputs[datum_idx]["logprobs"].to_torch()
            w = all_sft_data[datum_idx].loss_fn_inputs["weights"].to_torch()
            gt_logprobs = logprobs[w > 0]
            reward = torch.clamp(gt_logprobs, min=-5.0).mean().item()
            rewards.append(reward)
            datum_idx += 1

        total_gt_tokens += len(gt_tokens) * num_trajs
        all_logprob_rewards.extend(rewards)

        # GRPO normalize within this group
        rewards_t = torch.tensor(rewards)
        advantages_G = rewards_t - rewards_t.mean()

        logger.info(
            f"ELBO group rewards: mean={rewards_t.mean().item():.4f}, "
            f"std={rewards_t.std().item() if len(rewards) > 1 else 0:.4f}"
        )

        # Build CoT-only RL datums (transitions[:2] = Think + Revise)
        for traj, adv in zip(traj_group.trajectories_G, advantages_G):
            cot_traj = Trajectory(
                transitions=traj.transitions[:2],
                final_ob=traj.transitions[2].ob,
            )
            new_data = trajectory_to_data(cot_traj, float(adv))
            all_rl_data.extend([_remove_mask(d) for d in new_data])

    # --- RL forward_backward (returns future for pipelining with optim_step) ---
    rl_future = None
    if all_rl_data:
        logger.info(f"ELBO: RL forward_backward on {len(all_rl_data)} datums (CoT tokens)")
        rl_future = await training_client.forward_backward_async(
            all_rl_data, loss_fn="importance_sampling",
        )

    total_sft_loss = sft_result.metrics.get("loss:sum", 0.0)
    rewards_all = torch.tensor(all_logprob_rewards)
    metrics = {
        "elbo/sft_loss": total_sft_loss / total_gt_tokens if total_gt_tokens > 0 else 0.0,
        "elbo/logprob_reward_mean": rewards_all.mean().item(),
        "elbo/logprob_reward_std": rewards_all.std().item() if len(all_logprob_rewards) > 1 else 0.0,
    }

    if eval_with_llm_judge:
        judge_rewards = []
        for tg in traj_groups:
            judge_rewards.extend(tg.get_total_rewards())
        metrics["elbo/llm_judge_reward_mean"] = (
            sum(judge_rewards) / len(judge_rewards) if judge_rewards else 0.0
        )

    return rl_future, metrics


async def main_elbo(cfg: train.Config, eval_with_llm_judge: bool = False):
    """Main ELBO training loop for offline LongNAP.

    Mirrors train.main() setup and do_sync_training() loop, but replaces
    the standard training step with the 2-stage ELBO logic.

    Args:
        cfg: Training configuration (same Config used by train.main).
        eval_with_llm_judge: If True, also log LLM judge reward alongside ELBO rewards.
    """
    # --- Setup (mirrors train.main) ---
    ml_logger = ml_log.setup_logging(
        log_dir=cfg.log_path,
        wandb_project=cfg.wandb_project,
        config=cfg,
        wandb_name=cfg.wandb_name,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("pylatexenc").setLevel(logging.WARNING)

    resume_info = checkpoint_utils.get_last_checkpoint(cfg.log_path)
    start_batch = resume_info["batch"] if resume_info else 0

    service_client = tinker.ServiceClient(base_url=cfg.base_url)
    if resume_info:
        training_client = (
            await service_client.create_training_client_from_state_with_optimizer_async(
                resume_info["state_path"]
            )
        )
        logger.info(f"Resumed ELBO training from {resume_info['state_path']}")
    elif cfg.load_checkpoint_path:
        training_client = await service_client.create_training_client_from_state_async(
            cfg.load_checkpoint_path
        )
        logger.info(f"Loaded weights from {cfg.load_checkpoint_path}")
    else:
        training_client = await service_client.create_lora_training_client_async(
            cfg.model_name, rank=cfg.lora_rank
        )

    tokenizer = training_client.get_tokenizer()
    dataset, _maybe_test_dataset = await cfg.dataset_builder()
    evaluators = [evaluator() for evaluator in cfg.evaluator_builders]
    num_batches = len(dataset)
    logger.info(f"ELBO training: {num_batches} batches")

    # Initial sampling client
    sampling_client, _ = await save_checkpoint_and_get_sampling_client(
        training_client, start_batch, cfg.log_path, cfg.save_every, start_batch, cfg.ttl_seconds
    )

    adam_params = tinker.AdamParams(learning_rate=cfg.learning_rate, beta1=0.9, beta2=0.95, eps=1e-8)

    # --- Training loop (mirrors do_sync_training) ---
    for i_batch in range(start_batch, num_batches):
        metrics: dict[str, Any] = {
            "progress/batch": i_batch,
            "optim/lr": cfg.learning_rate,
            "progress/done_frac": (i_batch + 1) / num_batches,
        }
        t_start = time.time()

        # Evals
        if cfg.eval_every > 0 and i_batch % cfg.eval_every == 0:
            eval_metrics = await run_evaluations_parallel(
                evaluators, sampling_client, cfg, i_batch
            )
            metrics.update(eval_metrics)

        # Rollouts
        builders = dataset.get_batch(i_batch)

        with _get_logtree_scope(
            log_path=cfg.log_path,
            num_groups_to_log=cfg.num_groups_to_log,
            f_name=f"elbo_iteration_{i_batch:06d}",
            scope_name=f"ELBO Iteration {i_batch}",
        ):
            traj_groups = await gather_with_progress(
                (
                    do_group_rollout_and_filter_constant_reward(
                        sampling_client,
                        builder,
                        max_tokens=cfg.max_tokens,
                        temperature=cfg.temperature,
                        do_remove_constant_reward_groups=False,
                        enable_logging=i < cfg.num_groups_to_log,
                    )
                    for i, builder in enumerate(builders)
                ),
                desc=f"ELBO batch {i_batch}",
            )

        # Filter None groups (constant reward filtering)
        valid = [(tg, b) for tg, b in zip(traj_groups, builders) if tg is not None]
        if not valid:
            logger.warning(f"Batch {i_batch}: no valid trajectory groups, skipping")
            continue
        valid_traj_groups, valid_builders = zip(*valid)
        valid_traj_groups = list(valid_traj_groups)
        valid_builders = list(valid_builders)

        # Log sample trajectories
        for tg in valid_traj_groups[: cfg.num_groups_to_log]:
            print_group(tg, tokenizer)

        # ELBO training step
        rl_future, elbo_metrics = await elbo_train_step(
            training_client, tokenizer, valid_traj_groups, valid_builders, eval_with_llm_judge
        )
        metrics.update(elbo_metrics)

        # Optim step (pipelined with RL forward_backward)
        optim_future = await training_client.optim_step_async(adam_params)

        # Consume results
        if rl_future is not None:
            rl_result = await rl_future.result_async()
            metrics["train/rl_loss"] = rl_result.metrics.get("loss:sum", 0.0)
        await optim_future.result_async()

        # Checkpoint + new sampler
        sampling_client, ckpt_metrics = await save_checkpoint_and_get_sampling_client(
            training_client, i_batch + 1, cfg.log_path, cfg.save_every, start_batch, cfg.ttl_seconds
        )
        metrics.update(ckpt_metrics)

        metrics["time/total"] = time.time() - t_start
        ml_logger.log_metrics(metrics, step=i_batch)

    # Final checkpoint
    if start_batch < num_batches:
        await checkpoint_utils.save_checkpoint_async(
            training_client=training_client,
            name="final",
            log_path=cfg.log_path,
            kind="both",
            loop_state={"batch": num_batches},
            ttl_seconds=cfg.ttl_seconds,
        )

    ml_logger.close()
    logger.info("ELBO training completed")

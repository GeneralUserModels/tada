"""
Online trainer using the Env abstraction.

Manages the streaming training loop: rollouts → batched forward_backward → optim_step.
"""

import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Empty
from typing import Any, Dict, List, Optional

import tinker
from tinker.types import AdamParams
from tinker_cookbook.completers import TinkerTokenCompleter
from tinker_cookbook.renderers.qwen3 import Qwen3VLInstructRenderer
from tinker_cookbook.rl.data_processing import assemble_training_data, compute_advantages, trajectory_to_data
from tinker_cookbook.rl.train import _remove_mask
from tinker_cookbook.rl.rollouts import do_group_rollout
from tinker_cookbook.rl.types import Trajectory
from tinker_cookbook.supervised.common import datum_from_model_input_weights
from tinker_cookbook.image_processing_utils import get_image_processor
from tinker_cookbook.tokenizer_utils import get_tokenizer

from powernap.longnap.env import LongNAPEnvGroupBuilder
from powernap.longnap.retrievers import InMemoryBM25Temporal, jaccard_ngrams
from powernap.longnap.scorer import create_reward_scorer
from powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION, TASK_DESCRIPTION_WITH_IMAGES, build_actions_block,
)

import wandb
import pandas as pd

logger = logging.getLogger(__name__)


def make_sample(
    buffer: List[Dict],
    past_len: int,
    future_len: int,
    num_imgs_per_sample: int = 0,
) -> Dict[str, Any]:
    """
    Create a sample from a buffer of labeled actions.

    Args:
        buffer: List of labeled action dicts
        past_len: Number of past actions to include
        future_len: Number of future actions (ground truth)
        num_imgs_per_sample: Number of images to include (from most recent actions)

    Returns a dict with 'messages' for the renderer.
    """
    from PIL import ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True

    window = buffer[-(past_len + future_len):]
    past = window[:past_len]
    future = window[past_len:]

    past_actions_block = build_actions_block(past)
    future_actions = build_actions_block(future)

    # Build content - optionally include images
    if num_imgs_per_sample > 0:
        # Collect images from the most recent N actions
        image_content = []
        for i in range(past_len):
            if i >= (past_len - num_imgs_per_sample):
                img = past[i].get("img")
                if img is not None:
                    image_content.append({"type": "image", "image": img.convert("RGB")})

        if image_content:
            content = image_content + [
                {"type": "text", "text": TASK_DESCRIPTION_WITH_IMAGES + "\n\n" + past_actions_block}
            ]
        else:
            # No images loaded successfully, fall back to text-only
            content = TASK_DESCRIPTION + "\n\n" + past_actions_block
    else:
        content = TASK_DESCRIPTION + "\n\n" + past_actions_block

    messages = [{
        "role": "user",
        "content": content,
    }]

    start_ts = datetime.strptime(past[0]["start_time"], "%Y-%m-%d_%H-%M-%S-%f").timestamp()
    end_ts = datetime.strptime(future[-1]["start_time"], "%Y-%m-%d_%H-%M-%S-%f").timestamp()

    return {
        "messages": messages,
        "solution": future_actions,
        "ts": start_ts,
        "end_ts": end_ts,
        "future_len": future_len,
        "past_len": past_len,
        "past_actions": past_actions_block,
    }

class OnlineEnvTrainer:
    """
    Online trainer using the Env abstraction.

    This manages the training loop for streaming data, using LongNAPEnv
    for the multi-turn Think → Revise → Actions flow.
    """

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-VL-30B-A3B-Instruct",
        reward_llm: str = "gemini/gemini-3-flash-preview",
        num_generations: int = 8,
        learning_rate: float = 1e-5,
        max_tokens: int = 512,
        temperature: float = 1.0,
        lora_rank: int = 32,
        num_imgs_per_sample: int = 0,
        retrieval_top_k: int = 10,
        retrieval_mmr_k: int = 5,
        retrieval_mmr_alpha: float = 0.5,
        retrieval_time_decay_lambda: float = 0.5,
        dedup_threshold: float = 0.8,
        log_dir: str = "./logs",
        log_to_wandb: bool = False,
        wandb_project: str = "longnap-online",
        wandb_run_name: str = "longnap-online",
        checkpoint_every_n_steps: int = 0,
        resume_from_checkpoint: Optional[str] = None,
        retriever_checkpoint: Optional[str] = None,
        sampler_ttl_seconds: Optional[int] = 60,
        loss_mode: str = "llm_judge",
        eval_with_llm_judge: bool = False,
    ):
        self.model_name = model_name
        self.loss_mode = loss_mode
        self.eval_with_llm_judge = eval_with_llm_judge
        self.sampler_ttl_seconds = sampler_ttl_seconds
        self.num_generations = num_generations
        self.learning_rate = learning_rate
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.log_dir = log_dir
        self.log_to_wandb = log_to_wandb and wandb is not None
        self.checkpoint_every_n_steps = checkpoint_every_n_steps
        self.run_name = wandb_run_name

        # Initialize Tinker clients
        self.service_client = tinker.ServiceClient()
        self.rest_client = self.service_client.create_rest_client()

        # Resolve checkpoint path early (before creating training client)
        self._resolved_checkpoint = self._resolve_checkpoint_static(resume_from_checkpoint, log_dir)

        # Create training client - use create_training_client_from_state if resuming from checkpoint
        # This supports cross-session checkpoint loading
        if self._resolved_checkpoint:
            logger.info(f"Creating training client from checkpoint: {self._resolved_checkpoint}")
            self.training_client = self.service_client.create_training_client_from_state(
                self._resolved_checkpoint
            )
        else:
            self.training_client = self.service_client.create_lora_training_client(
                base_model=model_name,
                rank=lora_rank,
            )

        self.num_imgs_per_sample = num_imgs_per_sample
        self._last_checkpoint_path: Optional[str] = None
        self._last_retriever_checkpoint_path: Optional[str] = None

        # Get tokenizer and renderer
        self.tokenizer = get_tokenizer(model_name)
        image_processor = get_image_processor(model_name)

        # Use Qwen3VLInstructRenderer with strip_thinking_from_history=False for multi-turn RL
        self.renderer = Qwen3VLInstructRenderer(
            self.tokenizer, image_processor, strip_thinking_from_history=False
        )

        # Save initial weights for sampler
        save_result = self.training_client.save_weights_for_sampler(
            name=f'{self.run_name}.model',
            ttl_seconds=self.sampler_ttl_seconds,
        ).result()
        self.latest_sampler_path = save_result.path
        self.sampling_client = self.service_client.create_sampling_client(
            model_path=self.latest_sampler_path
        )

        # Create retriever
        def dedup_fn(a, b):
            return jaccard_ngrams(a, b, n=3)

        self.retriever = InMemoryBM25Temporal(
            dedup_threshold=dedup_threshold,
            dedup_sim_fn=dedup_fn,
        )

        # Load retriever from explicit checkpoint path (e.g., from offline training)
        if retriever_checkpoint:
            self.retriever.load_checkpoint(retriever_checkpoint)
            self._last_retriever_checkpoint_path = retriever_checkpoint
            logger.info(f"Loaded retriever from {retriever_checkpoint} (N={self.retriever.N})")

        # Create reward scorer
        if self.loss_mode == "logprob_elbo" and not self.eval_with_llm_judge:
            async def _dummy_scorer(actions, ground_truth):
                return {"reward": 0.0, "accuracy": 0.0, "formatting": 0.0, "penalty": 0.0}
            self.reward_scorer = _dummy_scorer
        else:
            self.reward_scorer = create_reward_scorer(reward_llm=reward_llm)

        # Retrieval parameters
        self.retrieval_top_k = retrieval_top_k
        self.retrieval_mmr_k = retrieval_mmr_k
        self.retrieval_mmr_alpha = retrieval_mmr_alpha
        self.retrieval_time_decay_lambda = retrieval_time_decay_lambda

        # Training state
        self._step = 0
        self._start_time = None

        # Initialize wandb
        if self.log_to_wandb:
            wandb.init(
                project=wandb_project,
                name=wandb_run_name,
                config={
                    "model": model_name,
                    "reward_llm": reward_llm,
                    "max_tokens": max_tokens,
                    "num_generations": num_generations,
                    "temperature": temperature,
                    "learning_rate": learning_rate,
                }
            )

        # Handle checkpoint resume (restore step counter, retriever, etc.)
        if self._resolved_checkpoint:
            self._restore_checkpoint_metadata(self._resolved_checkpoint)

    @staticmethod
    def _resolve_checkpoint_static(checkpoint_path: Optional[str], log_dir: str) -> Optional[str]:
        """Resolve 'auto' to the latest checkpoint from checkpoints.jsonl, or return as-is.

        Static method so it can be called before self is fully initialized.
        """
        if not checkpoint_path:
            return None
        if checkpoint_path != "auto":
            return checkpoint_path
        ckpt_file = Path(log_dir) / "checkpoints.jsonl"
        if not ckpt_file.exists():
            logger.warning(f"No checkpoints.jsonl found in {log_dir}")
            return None
        last = None
        for line in ckpt_file.read_text().strip().splitlines():
            entry = json.loads(line)
            if "state_path" in entry:
                last = entry
        if last:
            logger.info(f"Auto-resolved checkpoint: {last['state_path']}")
            return last["state_path"]
        logger.warning("No valid checkpoints found in checkpoints.jsonl")
        return None

    def _resolve_checkpoint(self, checkpoint_path):
        """Resolve 'auto' to the latest checkpoint. Instance method wrapper."""
        return self._resolve_checkpoint_static(checkpoint_path, self.log_dir)

    def _get_checkpoint_entry(self, state_path):
        """Look up the full checkpoint entry for a given state_path from checkpoints.jsonl."""
        ckpt_file = Path(self.log_dir) / "checkpoints.jsonl"
        if not ckpt_file.exists():
            return None
        for line in ckpt_file.read_text().strip().splitlines():
            entry = json.loads(line)
            if entry.get("state_path") == state_path:
                return entry
        return None

    def _get_retriever_path_for_checkpoint(self, state_path):
        """Look up the retriever path for a given state_path from checkpoints.jsonl."""
        entry = self._get_checkpoint_entry(state_path)
        return entry.get("retriever_path") if entry else None

    def _restore_checkpoint_metadata(self, checkpoint_path):
        """Restore metadata from checkpoint (step counter, retriever) without loading model state.

        Used when training client was already initialized from state via create_training_client_from_state.
        """
        logger.info(f"Restoring checkpoint metadata from {checkpoint_path}...")

        # Restore step counter and checkpoint paths from the checkpoint entry
        entry = self._get_checkpoint_entry(checkpoint_path)
        if entry:
            self._step = entry.get("step", 0)
            self._last_checkpoint_path = checkpoint_path
            retriever_path = entry.get("retriever_path")
            self.retriever.load_checkpoint(retriever_path)
            self._last_retriever_checkpoint_path = retriever_path
            logger.info(f"Resumed from step {self._step}")
        else:
            logger.warning(f"No checkpoint entry found for {checkpoint_path}, starting from step 0")

        logger.info(f"Successfully restored checkpoint metadata from {checkpoint_path}")

    def refresh_sampler(self):
        """Re-save weights and recreate sampling client (e.g. after pause/resume)."""
        save_result = self.training_client.save_weights_for_sampler(
            name=f'{self.run_name}.model',
            ttl_seconds=self.sampler_ttl_seconds,
        ).result()
        self.latest_sampler_path = save_result.path
        self.sampling_client = self.service_client.create_sampling_client(
            model_path=self.latest_sampler_path
        )
        logger.info(f"Refreshed sampler: {self.latest_sampler_path}")

    async def _save_checkpoint(self, step):
        """Save a checkpoint and record it to checkpoints.jsonl. Deletes previous checkpoint."""
        checkpoint_name = f"{self.run_name}.checkpoint_step_{step:06d}"
        save_result = self.training_client.save_state(name=checkpoint_name).result()
        state_path = save_result.path
        logger.info(f"Saved checkpoint at step {step}: {state_path}")

        # Save retriever checkpoint
        retriever_path = Path(self.log_dir) / f"retriever_step_{step:06d}.json.gz"
        self.retriever.save_checkpoint(str(retriever_path))
        logger.info(f"Saved retriever checkpoint at step {step}: {retriever_path}")

        # Delete previous model checkpoint to only keep the latest
        if self._last_checkpoint_path:
            try:
                await self.rest_client.delete_checkpoint_from_tinker_path_async(
                    self._last_checkpoint_path
                )
                logger.info(f"Deleted previous checkpoint: {self._last_checkpoint_path}")
            except Exception as e:
                logger.warning(f"Failed to delete previous checkpoint: {e}")

        # Delete previous retriever checkpoint to only keep the latest
        if self._last_retriever_checkpoint_path:
            try:
                Path(self._last_retriever_checkpoint_path).unlink()
                logger.info(f"Deleted previous retriever checkpoint: {self._last_retriever_checkpoint_path}")
            except Exception as e:
                logger.warning(f"Failed to delete previous retriever checkpoint: {e}")

        self._last_checkpoint_path = state_path
        self._last_retriever_checkpoint_path = str(retriever_path)

        ckpt_file = Path(self.log_dir) / "checkpoints.jsonl"
        ckpt_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {"name": checkpoint_name, "step": step, "state_path": state_path, "retriever_path": str(retriever_path)}
        with open(ckpt_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return state_path

    async def _rollout_one_sample(self, sample: Dict[str, Any]):
        """Run rollout only (no forward_backward). Returns (TrajectoryGroup, sample)."""
        builder = LongNAPEnvGroupBuilder(
            input_data=sample,
            renderer=self.renderer,
            tokenizer=self.tokenizer,
            retriever=self.retriever,
            reward_scorer=self.reward_scorer,
            num_envs=self.num_generations,
            retrieval_top_k=self.retrieval_top_k,
            retrieval_mmr_k=self.retrieval_mmr_k,
            retrieval_mmr_alpha=self.retrieval_mmr_alpha,
            retrieval_time_decay_lambda=self.retrieval_time_decay_lambda,
        )

        policy = TinkerTokenCompleter(
            self.sampling_client,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        traj_group = await do_group_rollout(builder, policy)
        return traj_group, sample, builder

    def _train_batch_llm_judge(self, traj_groups: list, samples: list):
        """Compute advantages and one batched forward_backward for all groups.

        Returns:
            (fwdbwd_future_or_None, extra_metrics)
        """
        all_data = []
        for traj_group in traj_groups:
            advantages = compute_advantages([traj_group])
            data_D, _ = assemble_training_data([traj_group], advantages)
            all_data.extend([_remove_mask(d) for d in data_D])

        if not all_data:
            logger.warning("No training data produced for batch")
            return None, {}

        fwdbwd_future = self.training_client.forward_backward(
            all_data, loss_fn="importance_sampling",
        )
        return fwdbwd_future, {}

    def _train_batch_elbo(self, traj_groups: list, samples: list, builders: list = None):
        """Batched ELBO training: one SFT forward_backward (blocking) then one RL forward_backward.

        Returns:
            (rl_fwdbwd_future_or_None, extra_metrics)
        """
        import torch

        # --- Build ALL SFT datums across all groups ---
        all_sft_data = []
        group_traj_counts = []  # track num_trajs per group for reward extraction
        for traj_group, sample in zip(traj_groups, samples):
            gt_tokens = self.tokenizer.encode(sample["solution"], add_special_tokens=False)
            num_trajs = len(traj_group.trajectories_G)
            group_traj_counts.append((num_trajs, len(gt_tokens)))
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

        # --- 1 SFT forward_backward — BLOCKING (need logprobs for reward) ---
        logger.info(f"ELBO batch: SFT forward_backward on {len(all_sft_data)} datums")
        while True:
            try:
                sft_result = self.training_client.forward_backward(
                    all_sft_data, loss_fn="cross_entropy",
                ).result()
                break
            except Exception as e:
                logger.warning(f"ELBO SFT forward_backward failed: {e}. Retrying in 120s...")
                time.sleep(120)

        # --- Extract rewards per trajectory, GRPO normalize per group ---
        all_rl_data = []
        datum_idx = 0
        total_gt_tokens = 0
        all_logprob_rewards = []

        _builders = builders or [None] * len(traj_groups)
        for traj_group, sample, builder in zip(traj_groups, samples, _builders):
            gt_tokens = self.tokenizer.encode(sample["solution"], add_special_tokens=False)
            num_trajs = len(traj_group.trajectories_G)
            rewards = []
            for i in range(num_trajs):
                logprobs = sft_result.loss_fn_outputs[datum_idx]["logprobs"].to_torch()
                w = all_sft_data[datum_idx].loss_fn_inputs["weights"].to_torch()
                gt_logprobs = logprobs[w > 0]
                reward = torch.clamp(gt_logprobs, min=-5.0).mean().item()
                rewards.append(reward)
                datum_idx += 1

            total_gt_tokens += len(gt_tokens) * num_trajs
            all_logprob_rewards.extend(rewards)

            # Add ELBO winner to retriever
            if builder is not None:
                builder.add_elbo_winner_to_retriever(rewards)

            # GRPO normalize within this group
            rewards_t = torch.tensor(rewards)
            advantages_G = rewards_t - rewards_t.mean()

            logger.info(
                f"ELBO group rewards: mean={rewards_t.mean().item():.4f}, "
                f"std={rewards_t.std().item() if len(rewards) > 1 else 0:.4f}"
            )

            # Build CoT-only RL datums
            for traj, adv in zip(traj_group.trajectories_G, advantages_G):
                cot_traj = Trajectory(
                    transitions=traj.transitions[:2],
                    final_ob=traj.transitions[2].ob,
                )
                new_data = trajectory_to_data(cot_traj, float(adv))
                all_rl_data.extend([_remove_mask(d) for d in new_data])

        # --- 1 RL forward_backward ---
        rl_fwdbwd_future = None
        if all_rl_data:
            logger.info(f"ELBO batch: RL forward_backward on {len(all_rl_data)} datums (CoT tokens)")
            while True:
                try:
                    rl_fwdbwd_future = self.training_client.forward_backward(
                        all_rl_data, loss_fn="importance_sampling",
                    )
                    break
                except Exception as e:
                    logger.warning(f"ELBO RL forward_backward failed: {e}. Retrying in 120s...")
                    time.sleep(120)

        total_sft_loss = sft_result.metrics.get("loss:sum", 0.0)
        rewards_all = torch.tensor(all_logprob_rewards)
        extra_metrics = {
            "sft_loss": total_sft_loss / total_gt_tokens if total_gt_tokens > 0 else 0.0,
            "logprob_reward_mean": rewards_all.mean().item(),
            "logprob_reward_std": rewards_all.std().item() if len(all_logprob_rewards) > 1 else 0.0,
        }

        if self.eval_with_llm_judge:
            judge_rewards = []
            for tg in traj_groups:
                judge_rewards.extend(tg.get_total_rewards())
            extra_metrics["llm_judge_reward_mean"] = sum(judge_rewards) / len(judge_rewards) if judge_rewards else 0.0

        return rl_fwdbwd_future, extra_metrics

    def _log_rollouts_to_wandb(self, trajectory_groups: list, samples: list, builders: list = None):
        """Log rollouts to wandb as a table."""
        if not self.log_to_wandb or wandb is None or wandb.run is None or pd is None:
            return
        
        table_data = {
            "step": [],
            "prompt": [],
            "think": [],
            "revise": [],
            "actions": [],
            "ground_truth": [],
            "reward": [],
            "accuracy": [],
            "formatting": [],
            "penalty": [],
        }
        
        _builders = builders or [None] * len(trajectory_groups)
        for traj_group, sample, builder in zip(trajectory_groups, samples, _builders):
            # Get prompt from sample
            prompt = sample.get("past_actions", "")
            
            # Get per-env score components from builder
            score_components_list = getattr(builder, '_score_components', None) if builder else None
            
            # Get completions and rewards from each trajectory
            for i, traj in enumerate(traj_group.trajectories_G):
                # Each trajectory has 3 transitions: Think, Revise, Actions
                # Decode each action to get the text
                think_text = ""
                revise_text = ""
                actions_text = ""
                
                if len(traj.transitions) > 0:
                    think_text = self.tokenizer.decode(traj.transitions[0].ac.tokens, skip_special_tokens=True)
                if len(traj.transitions) > 1:
                    revise_text = self.tokenizer.decode(traj.transitions[1].ac.tokens, skip_special_tokens=True)
                if len(traj.transitions) > 2:
                    actions_text = self.tokenizer.decode(traj.transitions[2].ac.tokens, skip_special_tokens=True)
                
                # Get total reward (only from the final actions phase)
                reward = sum(trans.reward for trans in traj.transitions)
                
                # Get score components for this trajectory
                sc = (score_components_list[i] if score_components_list and i < len(score_components_list)
                      else {"accuracy": 0.0, "formatting": 0.0, "penalty": 0.0})
                
                table_data["step"].append(self._step)
                table_data["prompt"].append(prompt)
                table_data["think"].append(think_text)
                table_data["revise"].append(revise_text)
                table_data["actions"].append(actions_text)
                table_data["ground_truth"].append(sample.get("solution", ""))
                table_data["reward"].append(reward)
                table_data["accuracy"].append(sc["accuracy"])
                table_data["formatting"].append(sc["formatting"])
                table_data["penalty"].append(sc["penalty"])
        
        df = pd.DataFrame(table_data)
        wandb.log({"rollouts": wandb.Table(dataframe=df)})

    async def _finish_step(
        self,
        fwdbwd_futures: list,
        trajectory_groups: list,
        step_start: float,
        extra_metrics_list: Optional[List[Dict[str, float]]] = None,
        samples: Optional[list] = None,
        builders: Optional[list] = None,
    ) -> Dict[str, float]:

        """Complete one optimizer step after batched forward_backward.

        Runs optim_step (pipelined with forward_backward), waits for results,
        updates sampler, logs metrics, checkpoints.
        """
        if not fwdbwd_futures:
            logger.warning("No forward_backward futures to process")
            return {}

        print(f"[train] step {self._step}: optim step...")
        optim_future = self.training_client.optim_step(
            AdamParams(learning_rate=self.learning_rate, beta1=0.9, beta2=0.95, eps=1e-8)
        )

        # Wait for all forward_backward results (infinite retry on failure)
        total_loss = 0.0
        for f in fwdbwd_futures:
            while True:
                try:
                    result = f.result()
                    break
                except Exception as e:
                    logger.warning(f"forward_backward failed: {e}. Retrying in 120s...")
                    time.sleep(120)
            total_loss += result.metrics.get("loss:sum", 0.0)
        while True:
            try:
                optim_result = optim_future.result()
                break
            except Exception as e:
                logger.warning(f"optim_step failed: {e}. Retrying in 120s...")
                time.sleep(120)

        # Update sampling client (infinite retry on failure)
        while True:
            try:
                save_result = self.training_client.save_weights_for_sampler(
                    name=f'{self.run_name}.model-step-{self._step}',
                    ttl_seconds=self.sampler_ttl_seconds,
                ).result()
                self.latest_sampler_path = save_result.path
                self.sampling_client = self.service_client.create_sampling_client(
                    model_path=self.latest_sampler_path
                )
                break
            except Exception as e:
                logger.warning(f"save_weights_for_sampler failed: {e}. Retrying in 120s...")
                time.sleep(120)

        # Compute metrics
        all_rewards = []
        for traj_group in trajectory_groups:
            all_rewards.extend(traj_group.get_total_rewards())

        reward_mean = sum(all_rewards) / len(all_rewards) if all_rewards else 0.0
        reward_std = (
            (sum((r - reward_mean)**2 for r in all_rewards) / len(all_rewards))**0.5
            if all_rewards else 0.0
        )

        metrics = {
            "train/step": self._step,
            "train/loss": total_loss / len(fwdbwd_futures),
            "train/reward_mean": reward_mean,
            "train/reward_std": reward_std,
            "train/num_trajectories": len(all_rewards),
            "train/step_time": time.time() - step_start,
            "train/retriever_size": self.retriever.N,
        }

        # Aggregate score components from builders
        _builders = builders or []
        all_accuracy = []
        all_formatting = []
        all_penalty = []
        for builder in _builders:
            for sc in getattr(builder, '_score_components', []):
                all_accuracy.append(sc["accuracy"])
                all_formatting.append(sc["formatting"])
                all_penalty.append(sc["penalty"])
        if all_accuracy:
            metrics["train/accuracy_mean"] = sum(all_accuracy) / len(all_accuracy)
            metrics["train/formatting_mean"] = sum(all_formatting) / len(all_formatting)
            metrics["train/penalty_mean"] = sum(all_penalty) / len(all_penalty)

        # Aggregate extra metrics from ELBO mode
        if extra_metrics_list:
            sft_losses = [m["sft_loss"] for m in extra_metrics_list if "sft_loss" in m]
            if sft_losses:
                metrics["train/sft_loss"] = sum(sft_losses) / len(sft_losses)
            lp_rewards = [m["logprob_reward_mean"] for m in extra_metrics_list if "logprob_reward_mean" in m]
            if lp_rewards:
                metrics["train/logprob_reward_mean"] = sum(lp_rewards) / len(lp_rewards)
                metrics["train/logprob_reward_std"] = (
                    sum(m.get("logprob_reward_std", 0) for m in extra_metrics_list) / len(lp_rewards)
                )
            judge_rewards = [m["llm_judge_reward_mean"] for m in extra_metrics_list if "llm_judge_reward_mean" in m]
            if judge_rewards:
                metrics["train/llm_judge_reward_mean"] = sum(judge_rewards) / len(judge_rewards)

        if self.log_to_wandb and wandb.run is not None:
            wandb.log(metrics)
            
            # Log rollouts table to wandb
            if samples:
                self._log_rollouts_to_wandb(trajectory_groups, samples, builders=builders)
        
        logger.info(
            f"Step {self._step}: loss={metrics['train/loss']:.4f}, "
            f"reward={reward_mean:.4f}±{reward_std:.4f}, "
            f"time={metrics['train/step_time']:.2f}s"
        )
        print(f"[train] step {self._step} completed in {metrics['train/step_time']:.2f}s")

        # Checkpoint
        if self.checkpoint_every_n_steps > 0 and (self._step + 1) % self.checkpoint_every_n_steps == 0:
            await self._save_checkpoint(self._step + 1)

        self._step += 1
        return metrics

    def run_streaming(self, recorder, label_queue, past_len: int, future_len: int,
                      batch_size: int, num_imgs_per_sample: int = 0,
                      shutdown_event: Optional[threading.Event] = None):
        """Main streaming training loop.

        Runs batch_size rollouts concurrently, then sends one batched
        forward_backward + optim_step (1-2 Tinker clock cycles per step).
        """
        asyncio.run(self._run_streaming_async(
            recorder, label_queue, past_len, future_len,
            batch_size, num_imgs_per_sample, shutdown_event,
        ))

    async def _run_streaming_async(self, recorder, label_queue, past_len: int, future_len: int,
                                   batch_size: int, num_imgs_per_sample: int = 0,
                                   shutdown_event: Optional[threading.Event] = None):
        """Async implementation of streaming training with batched forward_backward.

        Phase 1: Submit rollouts concurrently as samples arrive (up to batch_size).
        Phase 2: Gather all rollout results.
        Phase 3: One batched forward_backward + optim_step (1 clock cycle for LLM judge,
                 2 clock cycles for ELBO).
        """
        min_required = past_len + future_len
        buffer = []
        steps_completed = 0

        loop = asyncio.get_running_loop()

        async def get_from_queue():
            """Await items from threading Queue without CPU spinning."""
            while True:
                try:
                    return await loop.run_in_executor(
                        None, lambda: label_queue.get(timeout=1.0)
                    )
                except Empty:
                    if shutdown_event and shutdown_event.is_set():
                        return None
                    if not recorder.running and label_queue.empty():
                        return None

        def _should_run():
            if shutdown_event and shutdown_event.is_set():
                return False
            return recorder.running or not label_queue.empty()

        while _should_run():
            # === Collect and run one batch ===
            batch_rollouts = []
            pending_samples = []
            step_start = None

            queue_task = asyncio.create_task(get_from_queue())

            # Phase 1: Submit rollouts as samples arrive (up to batch_size)
            while len(batch_rollouts) < batch_size:
                if not _should_run():
                    break

                wait_tasks = {queue_task} | set(batch_rollouts)
                done, _ = await asyncio.wait(wait_tasks, return_when=asyncio.FIRST_COMPLETED)

                for task in done:
                    if task is queue_task:
                        record = task.result()
                        if record is None:
                            queue_task = None
                            break

                        buffer.append(record)
                        print(f"[train] buffer size: {len(buffer)}/{min_required}")

                        if len(buffer) >= min_required:
                            pending_samples.append(
                                make_sample(buffer, past_len, future_len, num_imgs_per_sample)
                            )

                        queue_task = asyncio.create_task(get_from_queue())

                while pending_samples and len(batch_rollouts) < batch_size:
                    sample = pending_samples.pop(0)
                    if step_start is None:
                        step_start = time.time()
                    idx = len(batch_rollouts) + 1
                    print(f"[train] step {self._step}: rollout {idx}/{batch_size}...")
                    rollout_task = asyncio.create_task(self._rollout_one_sample(sample))
                    batch_rollouts.append(rollout_task)

                if queue_task is None:
                    break

            # Cancel queue task while we finish this batch
            if queue_task and not queue_task.done():
                queue_task.cancel()
                try:
                    await queue_task
                except asyncio.CancelledError:
                    pass

            # Phase 2: Wait for all rollouts to complete
            if not batch_rollouts:
                continue

            results = await asyncio.gather(*batch_rollouts, return_exceptions=True)

            traj_groups = []
            samples_for_batch = []
            builders_for_batch = []
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Rollout failed: {r}")
                    continue
                traj_group, sample, builder = r
                traj_groups.append(traj_group)
                samples_for_batch.append(sample)
                builders_for_batch.append(builder)

            if not traj_groups:
                continue

            # Phase 3: Batched training (1-2 forward_backward calls instead of N)
            print(f"[train] step {self._step}: batched training on {len(traj_groups)} groups...")
            if self.loss_mode == "logprob_elbo":
                fwdbwd_future, extra_metrics = self._train_batch_elbo(traj_groups, samples_for_batch, builders_for_batch)
            else:
                fwdbwd_future, extra_metrics = self._train_batch_llm_judge(traj_groups, samples_for_batch)

            fwdbwd_futures = [fwdbwd_future] if fwdbwd_future is not None else []
            extra_metrics_list = [extra_metrics] if extra_metrics else []

            if fwdbwd_futures:
                await self._finish_step(fwdbwd_futures, traj_groups, step_start or time.time(), extra_metrics_list, samples_for_batch, builders=builders_for_batch)
                steps_completed += 1

                if wandb and wandb.run is not None:
                    wandb.log({
                        "pipeline/buffer_size": len(buffer),
                        "pipeline/batches_yielded": steps_completed,
                        "pipeline/label_queue_size": label_queue.qsize(),
                    })

                if len(buffer) > min_required:
                    buffer = buffer[-min_required:]

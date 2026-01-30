#!/usr/bin/env python3
"""
Online training pipeline using the Env abstraction.

Records screen → labels with LLM → trains with Env-based RL → predicts next actions.

This is the Env-based equivalent of run_online.py, providing cleaner multi-turn
training through the tinker_cookbook Env abstraction.
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import asyncio
import json
import logging
import re
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from queue import Queue, Empty
from typing import Any, Dict, List, Optional

# ActionOverlay MUST be imported before torch/transformers/PIL —
# PIL conflicts with AppKit's NSApplication on macOS.
from powernap.inference import ActionOverlay


def _load_heavy_imports():
    """Deferred imports that pull in torch/PIL. Call after overlay is created."""
    import tinker
    from tinker.types import AdamParams
    from transformers import AutoTokenizer
    from tinker_cookbook import model_info, renderers
    from tinker_cookbook.completers import TinkerTokenCompleter
    from tinker_cookbook.renderers.qwen3 import Qwen3VLInstructRenderer
    from tinker_cookbook.rl.data_processing import assemble_training_data, compute_advantages
    from tinker_cookbook.rl.train import _remove_mask
    from tinker_cookbook.rl.rollouts import do_group_rollout
    from tinker_cookbook.rl.types import TrajectoryGroup
    from tinker_cookbook.image_processing_utils import get_image_processor
    from tinker_cookbook.tokenizer_utils import get_tokenizer
    from powernap.napsack import OnlineRecorder, Labeler
    from powernap.longnap.env import LongNAPEnvGroupBuilder
    from powernap.longnap.retrievers import InMemoryBM25Temporal, jaccard_ngrams
    from powernap.longnap.scorer import create_reward_scorer
    from powernap.longnap.trainer_utils import TASK_DESCRIPTION, TASK_DESCRIPTION_WITH_IMAGES, build_actions_block
    from powernap.inference import Predictor
    from powernap.sleepwalk import SleepWalker

    try:
        import wandb
        wandb_available = True
    except ImportError:
        wandb = None
        wandb_available = False

    # Inject into module globals so the rest of the code can use them
    g = globals()
    g.update({
        "tinker": tinker, "AdamParams": AdamParams, "AutoTokenizer": AutoTokenizer,
        "model_info": model_info, "renderers": renderers,
        "TinkerTokenCompleter": TinkerTokenCompleter,
        "Qwen3VLInstructRenderer": Qwen3VLInstructRenderer,
        "assemble_training_data": assemble_training_data,
        "compute_advantages": compute_advantages, "_remove_mask": _remove_mask,
        "do_group_rollout": do_group_rollout, "TrajectoryGroup": TrajectoryGroup,
        "get_image_processor": get_image_processor, "get_tokenizer": get_tokenizer,
        "OnlineRecorder": OnlineRecorder, "Labeler": Labeler,
        "LongNAPEnvGroupBuilder": LongNAPEnvGroupBuilder,
        "InMemoryBM25Temporal": InMemoryBM25Temporal, "jaccard_ngrams": jaccard_ngrams,
        "create_reward_scorer": create_reward_scorer,
        "TASK_DESCRIPTION": TASK_DESCRIPTION,
        "TASK_DESCRIPTION_WITH_IMAGES": TASK_DESCRIPTION_WITH_IMAGES,
        "build_actions_block": build_actions_block,
        "Predictor": Predictor, "SleepWalker": SleepWalker,
        "wandb": wandb, "WANDB_AVAILABLE": wandb_available,
    })


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
    from PIL import Image, ImageFile
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
                img_path = past[i].get("img")
                if img_path and Path(img_path).exists():
                    try:
                        img = Image.open(img_path).convert("RGB")  # Convert to RGB for consistency
                        image_content.append({"type": "image", "image": img})
                    except Exception as e:
                        logger.warning(f"Failed to load image {img_path}: {e}")
        
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
        retrieval_mmr_k: int = 10,
        retrieval_mmr_alpha: float = 0.5,
        retrieval_time_decay_lambda: float = 0.5,
        dedup_threshold: float = 0.8,
        log_dir: str = "./logs",
        log_to_wandb: bool = False,
        wandb_project: str = "longnap-online",
        wandb_run_name: str = "longnap-online",
        checkpoint_every_n_steps: int = 0,
        resume_from_checkpoint: Optional[str] = None,
    ):
        self.model_name = model_name
        self.num_generations = num_generations
        self.learning_rate = learning_rate
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.log_dir = log_dir
        self.log_to_wandb = log_to_wandb and WANDB_AVAILABLE
        self.checkpoint_every_n_steps = checkpoint_every_n_steps
        self.run_name = wandb_run_name
        
        # Initialize Tinker clients
        self.service_client = tinker.ServiceClient()
        self.training_client = self.service_client.create_lora_training_client(
            base_model=model_name,
            rank=lora_rank,
        )
        self.num_imgs_per_sample = num_imgs_per_sample
        
        # Get tokenizer and renderer
        self.tokenizer = get_tokenizer(model_name)
        image_processor = get_image_processor(model_name)
        
        # Use Qwen3VLInstructRenderer with strip_thinking_from_history=False for multi-turn RL
        self.renderer = Qwen3VLInstructRenderer(
            self.tokenizer, image_processor, strip_thinking_from_history=False
        )
        
        # Save initial weights for sampler
        save_result = self.training_client.save_weights_for_sampler(
            name=f'{self.run_name}.model'
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
        
        # Create reward scorer
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
        
        # Handle checkpoint resume
        if resume_from_checkpoint:
            self._load_checkpoint(resume_from_checkpoint)

    def _resolve_checkpoint(self, checkpoint_path):
        """Resolve 'auto' to the latest checkpoint from checkpoints.jsonl, or return as-is."""
        if checkpoint_path != "auto":
            return checkpoint_path
        ckpt_file = Path(self.log_dir) / "checkpoints.jsonl"
        if not ckpt_file.exists():
            logger.warning(f"No checkpoints.jsonl found in {self.log_dir}")
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

    def _load_checkpoint(self, checkpoint_path):
        """Load a checkpoint. Supports 'auto' to pick the latest."""
        resolved = self._resolve_checkpoint(checkpoint_path)
        if not resolved:
            logger.warning("No checkpoint to load")
            return
        logger.info(f"Loading checkpoint from {resolved}...")
        self.training_client.load_state(resolved).result()
        save_result = self.training_client.save_weights_for_sampler(
            name=f'{self.run_name}.model-resumed'
        ).result()
        self.latest_sampler_path = save_result.path
        self.sampling_client = self.service_client.create_sampling_client(
            model_path=self.latest_sampler_path
        )
        logger.info(f"Successfully loaded checkpoint from {resolved}")

    def _save_checkpoint(self, step):
        """Save a checkpoint and record it to checkpoints.jsonl."""
        checkpoint_name = f"{self.run_name}.checkpoint_step_{step:06d}"
        save_result = self.training_client.save_state(name=checkpoint_name).result()
        state_path = save_result.path
        logger.info(f"Saved checkpoint at step {step}: {state_path}")

        ckpt_file = Path(self.log_dir) / "checkpoints.jsonl"
        ckpt_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {"name": checkpoint_name, "step": step, "state_path": state_path}
        with open(ckpt_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

        return state_path
    
    async def train_on_batch(self, batch: List[Dict[str, Any]]) -> Dict[str, float]:
        """
        Train on a batch of samples using the Env abstraction.
        
        Args:
            batch: List of sample dicts with 'messages', 'solution', etc.
            
        Returns:
            Dict of metrics
        """
        step_start = time.time()
        metrics = {}
        print(f"[train] step {self._step}: creating env builders for {len(batch)} samples...")
        
        # Create EnvGroupBuilders for each sample in the batch
        env_group_builders = []
        for sample in batch:
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
            env_group_builders.append(builder)
        
        # Create policy completer
        policy = TinkerTokenCompleter(
            self.sampling_client,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        print(f"[train] step {self._step}: running rollouts ({self.num_generations} generations per sample)...")
        
        # Run rollouts for all groups
        trajectory_groups: List[TrajectoryGroup] = []
        for i, builder in enumerate(env_group_builders):
            print(f"[train] step {self._step}: rollout {i+1}/{len(env_group_builders)}...")
            traj_group = await do_group_rollout(builder, policy)
            trajectory_groups.append(traj_group)
        
        # Compute advantages (GRPO-style per-group normalization)
        print(f"[train] step {self._step}: computing advantages...")
        advantages = compute_advantages(trajectory_groups)
        
        # Assemble training data
        data_D, metadata_D = assemble_training_data(trajectory_groups, advantages)
        
        if not data_D:
            logger.warning("No training data generated")
            return {"step": self._step, "loss": 0.0}
                
        # Forward-backward pass (remove mask like cookbook's train_step does)
        print(f"[train] step {self._step}: forward-backward pass...")
        fwdbwd_future = self.training_client.forward_backward(
            [_remove_mask(d) for d in data_D],
            loss_fn="importance_sampling",
        )
        
        # Optimizer step (pipelined)
        optim_future = self.training_client.optim_step(
            AdamParams(learning_rate=self.learning_rate)
        )
        
        # Wait for results
        print(f"[train] step {self._step}: waiting for training to complete...")
        fwdbwd_result = fwdbwd_future.result()
        optim_result = optim_future.result()
        
        # Update sampling client
        save_result = self.training_client.save_weights_for_sampler(
            name=f'{self.run_name}.model-step-{self._step}'
        ).result()
        self.latest_sampler_path = save_result.path
        self.sampling_client = self.service_client.create_sampling_client(
            model_path=self.latest_sampler_path
        )
        
        # Compute metrics
        all_rewards = []
        for traj_group in trajectory_groups:
            all_rewards.extend(traj_group.get_total_rewards())
        
        reward_mean = sum(all_rewards) / len(all_rewards) if all_rewards else 0.0
        reward_std = (
            (sum((r - reward_mean)**2 for r in all_rewards) / len(all_rewards))**0.5
            if all_rewards else 0.0
        )
        metrics["train/step"] = self._step
        metrics["train/loss"] = fwdbwd_result.metrics.get("loss:sum", 0.0)
        metrics["train/reward_mean"] = reward_mean
        metrics["train/reward_std"] = reward_std
        metrics["train/num_trajectories"] = len(all_rewards)
        metrics["train/step_time"] = time.time() - step_start
        metrics["train/retriever_size"] = self.retriever.N

        # Log to wandb
        if self.log_to_wandb and wandb.run is not None:
            wandb.log(metrics)

        # Console log
        logger.info(
            f"Step {self._step}: loss={metrics['train/loss']:.4f}, "
            f"reward={reward_mean:.4f}±{reward_std:.4f}, "
            f"time={metrics['train/step_time']:.2f}s"
        )
        
        print(f"[train] step {self._step} completed in {metrics['train/step_time']:.2f}s")

        # Checkpoint
        if self.checkpoint_every_n_steps > 0 and (self._step + 1) % self.checkpoint_every_n_steps == 0:
            self._save_checkpoint(self._step + 1)
        
        self._step += 1
        return metrics
    
    def train_sync(self, batch: List[Dict[str, Any]]) -> Dict[str, float]:
        """Synchronous wrapper for train_on_batch."""
        return asyncio.run(self.train_on_batch(batch))



def label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active):
    """Label incoming screen recordings and add to retriever."""

    label_count = 0
    skip_count = 0
    last_hash = None
    dedupe_threshold = 1

    import imagehash
    from PIL import Image, ImageFile
    ImageFile.LOAD_TRUNCATED_IMAGES = True

    for agg in recorder.iter_aggregations():
        # pack-style sanitization: skip if no screenshot
        screenshot_path = agg.request.screenshot_path
        if not screenshot_path or not Path(screenshot_path).exists():
            skip_count += 1
            continue

        # pack-style image dedup: skip if screenshot too similar to previous
        try:
            curr_hash = imagehash.phash(Image.open(screenshot_path))
            if last_hash is not None and (curr_hash - last_hash) <= dedupe_threshold:
                skip_count += 1
                print(f"[label] dedup skip (hamming={curr_hash - last_hash}, total skipped={skip_count})")
                continue
            last_hash = curr_hash
        except Exception:
            pass

        t0 = time.time()
        labeled = labeler.label(agg)
        latency = time.time() - t0
        label_count += 1
        print(f"[label] labeled action #{label_count}: {labeled['text'][:80]}... ({latency:.2f}s)")


        # always add to inference buffer
        inference_buffer.append(labeled)

        # only feed training data when sleepwalk is NOT active
        if not sleepwalk_active.is_set():
            ts = datetime.strptime(labeled["start_time"], "%Y-%m-%d_%H-%M-%S-%f")
            retriever.add(
                labeled["text"],
                event_ts=int(ts.timestamp()),
                namespace="train",
            )
            label_queue.put(labeled)

        if wandb and wandb.run is not None:
            log = {
                "pipeline/labels_total": label_count,
                "pipeline/label_latency_s": latency,
                "pipeline/label_text": wandb.Html(f"<pre>{labeled['text']}</pre>"),
            }

            if label_count % 10 == 1 and labeled.get("img") and Path(labeled["img"]).exists():
                log["pipeline/label_image"] = wandb.Image(
                    labeled["img"], caption=labeled["text"][:200],
                )

            wandb.log(log)


def batch_iter(recorder, label_queue, past_len, future_len, batch_size, num_imgs_per_sample=0):
    """Iterate over batches from the label queue."""
    min_required = past_len + future_len
    buffer = []
    batch = []
    batches_yielded = 0

    while recorder.running or not label_queue.empty():
        try:
            record = label_queue.get(timeout=1.0)
        except Empty:
            continue

        buffer.append(record)
        print(f"[train] buffer size: {len(buffer)}/{min_required} (need {batch_size} samples to start training)")

        if len(buffer) >= min_required:
            sample = make_sample(buffer, past_len, future_len, num_imgs_per_sample)
            batch.append(sample)
            print(f"[train] created sample, batch size: {len(batch)}/{batch_size}")

            if len(batch) >= batch_size:
                print(f"[train] yielding batch for training (step {batches_yielded + 1})")
                batches_yielded += 1

                if wandb and wandb.run is not None:
                    wandb.log({
                        "pipeline/buffer_size": len(buffer),
                        "pipeline/batches_yielded": batches_yielded,
                    })

                yield batch
                batch = []


def inference_loop(predictor, inference_buffer, trainer, recorder,
                   past_len, future_len, processor, predict_interval,
                   reward_llm, overlay, walker):
  
    executor = ThreadPoolExecutor(max_workers=8)
    pending_predictions = []  # (future, buffer_pos, seq)

    last_path = None
    last_buffer_len = 0
    last_submit_time = 0
    prediction_count = 0
    prediction_seq = 0
    latest_completed_seq = 0
    eval_count = 0
    pending_evals = []

    while recorder.running:
        # Pick up new checkpoint
        path = getattr(trainer, "latest_sampler_path", None)
        if path and path != last_path:
            predictor.model_path = path
            last_path = path
            print(f"[inference] using checkpoint: {path}")


        # submit new prediction when buffer has grown and enough time has passed
        cur_buffer_len = len(inference_buffer)
        now = time.time()
        if (overlay and overlay._visible and predictor.model_path
                and cur_buffer_len >= past_len
                and cur_buffer_len > last_buffer_len
                and now - last_submit_time >= predict_interval):
            last_buffer_len = cur_buffer_len
            buffer_pos = cur_buffer_len
            prediction_seq += 1

            model_path = predictor.model_path
            buffer_snapshot = list(inference_buffer[-past_len:])

            future = executor.submit(
                predictor.predict_from_snapshot,
                buffer_snapshot, future_len,
                model_path_override=model_path,
            )
            last_submit_time = now
            pending_predictions.append((future, buffer_pos, prediction_seq))
            print(f"[inference] submitted prediction seq {prediction_seq} (buffer={buffer_pos}, in-flight={len(pending_predictions)})")

        # collect completed predictions
        still_pending_preds = []
        for future, buf_pos, seq in pending_predictions:
            if future.done():
                result = future.result()
                prediction_count += 1

                print(f"[inference] prediction #{prediction_count} (seq {seq}) complete:")
                print(f"  actions: {result['actions']}")

                actions_parsed = bool(re.search(r"<action>", result["actions"]))

                if not actions_parsed:
                    print(f"[inference] prediction #{prediction_count}: no <action> tags, reward=0")
                else:
                    # track for eval scoring
                    pending_evals.append((result, buf_pos, future_len))

                    # update overlay/walker only if this is newer than the last displayed
                    if seq > latest_completed_seq:
                        latest_completed_seq = seq
                        if overlay and not walker.active.is_set():
                            overlay.update(result["actions"])
                        walker.latest_prediction = {"actions": result["actions"], "seq": seq}

                if wandb and wandb.run is not None:
                    wandb.log({
                        "inference/predictions_total": prediction_count,
                        "inference/in_flight": len(still_pending_preds),
                    })
            else:
                still_pending_preds.append((future, buf_pos, seq))
        pending_predictions = still_pending_preds

        # Check pending evals
        still_pending = []
        for result, buf_pos, fl in pending_evals:
            if len(inference_buffer) >= buf_pos + fl:
                ground_truth = build_actions_block(inference_buffer[buf_pos:buf_pos + fl])
                reward = predictor.score_prediction(result["actions"], ground_truth, reward_llm)
                eval_count += 1

                print(f"[inference] eval #{eval_count}: reward={reward:.2f}")

                if wandb and wandb.run is not None:
                    wandb.log({
                        "inference/reward": reward,
                        "inference/evals_total": eval_count,
                    })
            else:
                still_pending.append((result, buf_pos, fl))
        pending_evals = still_pending

        time.sleep(1)


def main():
    parser = argparse.ArgumentParser(
        description="Online training pipeline using Env abstraction"
    )

    # Recorder
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--buffer-seconds", type=int, default=12)
    parser.add_argument("--precision", type=str, choices=["accurate", "rough"], default="accurate")

    # Labeler
    parser.add_argument("--label-model", type=str, default="gemini/gemini-2.0-flash")

    # Trainer
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-VL-30B-A3B-Instruct")
    parser.add_argument("--reward-llm", type=str, default="gemini/gemini-3-flash-preview")
    parser.add_argument("--num-generations", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--max-completion-length", type=int, default=512)
    parser.add_argument("--num-imgs-per-sample", type=int, default=0, 
                        help="Number of images to include per sample (0 = text only)")

    # Pipeline
    parser.add_argument("--past-len", type=int, default=8)
    parser.add_argument("--future-len", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=2)

    # Inference
    parser.add_argument("--predict-every-n-seconds", type=int, default=10)
    parser.add_argument("--disable-inference", action="store_true")
    parser.add_argument("--no-overlay", action="store_true")


    parser.add_argument("--sleepwalk-model", type=str, default="gemini/gemini-3-flash-preview",
                        help="litellm model for SleepWalk computer-use agent")
    parser.add_argument("--sleepwalk-max-iter", type=int, default=5,
                        help="Max iterations per action for SleepWalk")


    parser.add_argument("--log-every-n-steps", type=int, default=1)
    parser.add_argument("--log-dir", type=str, default="./logs")
    parser.add_argument("--log-to-wandb", action="store_true")
    parser.add_argument("--wandb-project", type=str, default="longnap-online")
    parser.add_argument("--wandb-run-name", type=str, default="longnap-online-env")

    # Checkpointing
    parser.add_argument("--checkpoint-every-n-steps", type=int, default=0)
    parser.add_argument("--resume-from-checkpoint", type=str, default=None)

    args = parser.parse_args()

    # Create overlay FIRST — before torch/transformers/PIL are loaded.
    overlay = None
    if not args.disable_inference and not args.no_overlay:
        overlay = ActionOverlay()

    # Now load heavy imports (torch, transformers, tinker, etc.)
    _load_heavy_imports()

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Setup precision preset
    from record.constants import constants_manager
    constants_manager.set_preset(args.precision, verbose=False)

    # Tokenizer (for inference)
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)

    # Stage 1: Recorder
    recorder = OnlineRecorder(
        fps=args.fps,
        buffer_seconds=args.buffer_seconds,
        log_dir=args.log_dir,
    )

    # Stage 2: Labeler
    labeler = Labeler(model=args.label_model, log_dir=recorder.session_dir)

    # Stage 3: Trainer (using Env abstraction)
    trainer = OnlineEnvTrainer(
        model_name=args.model,
        reward_llm=args.reward_llm,
        num_generations=args.num_generations,
        learning_rate=args.learning_rate,
        max_tokens=args.max_completion_length,
        num_imgs_per_sample=args.num_imgs_per_sample,
        log_dir=args.log_dir,
        log_to_wandb=args.log_to_wandb,
        wandb_project=args.wandb_project,
        wandb_run_name=args.wandb_run_name,
        checkpoint_every_n_steps=args.checkpoint_every_n_steps,
        resume_from_checkpoint=args.resume_from_checkpoint,
    )

    # Stage 4: Predictor (shares retriever with trainer)
    predictor = Predictor(
        model_path=trainer.latest_sampler_path,
        max_tokens=args.max_completion_length,
        retriever=trainer.retriever,
        log_dir=recorder.session_dir,
    )

    # sleepwalk
    sleepwalk_active = threading.Event()
    inference_buffer = []

    walker = SleepWalker(
        model=args.sleepwalk_model,
        inference_buffer=inference_buffer,
        overlay=overlay,
        max_iterations=args.sleepwalk_max_iter,
    )

    # wire Ctrl+G to toggle sleepwalk
    if overlay:
        def on_sleepwalk_toggle():
            if walker.active.is_set():
                print("[sleepwalk] deactivating — resuming training data collection")
                walker.active.clear()
                sleepwalk_active.clear()
                overlay.update_sleepwalk(None, active=False)
            else:
                print("[sleepwalk] activating — pausing training data collection")
                walker.active.set()
                sleepwalk_active.set()
                overlay.update_sleepwalk(None, active=True)

        overlay.set_sleepwalk_callback(on_sleepwalk_toggle)


    label_queue = Queue()

    def shutdown(sig, frame):
        if overlay:
            overlay.close()
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Preload HIServices on main thread — pyobjc lazy loading isn't thread-safe,
    # and pynput's listener thread needs AXIsProcessTrusted() loaded before it starts.
    try:
        import HIServices
        HIServices.AXIsProcessTrusted()
    except Exception:
        pass

    recorder.start()

    # Label thread
    label_thread = threading.Thread(
        target=label_loop,
        args=(recorder, labeler, trainer.retriever, label_queue, inference_buffer, sleepwalk_active),
        daemon=True,
    )
    label_thread.start()

    # Inference thread
    if not args.disable_inference:
        inference_thread = threading.Thread(
            target=inference_loop,
            args=(predictor, inference_buffer, trainer, recorder,
                  args.past_len, args.future_len, tokenizer,
                  args.predict_every_n_seconds, args.reward_llm, overlay, walker),

            daemon=True,
        )
        inference_thread.start()


     # sleepwalk thread
    sleepwalk_thread = threading.Thread(target=walker.run, daemon=True)
    sleepwalk_thread.start()

    # Training loop (runs on background thread)
    data = batch_iter(
        recorder, label_queue, args.past_len, args.future_len, 
        args.batch_size, args.num_imgs_per_sample
    )

    def train_loop():
        for batch in data:
            trainer.train_sync(batch)
        
        if overlay:
            overlay.close()
        recorder.stop()

    train_thread = threading.Thread(target=train_loop, daemon=True)
    train_thread.start()

    # Main thread handles overlay or waits for training
    if overlay:
        overlay.run()
    else:
        train_thread.join()

    recorder.stop()


if __name__ == "__main__":
    main()

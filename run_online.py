#!/usr/bin/env python3
"""
Online training pipeline using the Env abstraction.

Records screen → labels with LLM → trains with Env-based RL → predicts next actions.
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import logging
import os
import signal
import threading
from queue import Queue

# ActionOverlay MUST be imported before torch/transformers/PIL —
# PIL conflicts with AppKit's NSApplication on macOS.
from powernap.inference import ActionOverlay


def main():
    parser = argparse.ArgumentParser(
        description="Online training pipeline using Env abstraction"
    )

    # Recorder
    parser.add_argument("--fps", type=int, default=5)
    parser.add_argument("--buffer-seconds", type=int, default=12)
    parser.add_argument("--precision", type=str, choices=["accurate", "rough"], default="accurate")
    parser.add_argument("--save-screenshots", action="store_true",
                        help="Save screenshots to disk (disabled by default)")
    parser.add_argument("--disable-events", type=str, nargs="*", default=None,
                        help="Event types to disable: move, scroll, click, key. "
                             "Default: ['move']. Use --disable-events (no args) to enable all.")

    # Labeler (video chunk-based)
    parser.add_argument("--chunk-size", type=int, default=60,
                        help="Number of screenshots per video chunk for labeling")
    parser.add_argument("--chunk-fps", type=int, default=1,
                        help="Video encoding framerate for labeling (1 = one frame per second)")
    parser.add_argument("--chunk-workers", type=int, default=4,
                        help="Number of parallel chunk processors")

    # Trainer
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-VL-30B-A3B-Instruct")
    parser.add_argument("--reward-llm", type=str, default="gemini/gemini-3-flash-preview")
    parser.add_argument("--num-generations", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--max-completion-length", type=int, default=512)
    parser.add_argument("--num-imgs-per-sample", type=int, default=2,
                        help="Number of images to include per sample (0 = text only)")
    parser.add_argument("--loss-mode", type=str, choices=["llm_judge", "logprob_elbo"],
                        default="llm_judge",
                        help="Loss formulation: LLM judge reward or logprob ELBO (paper 2601.04436)")
    parser.add_argument("--eval-with-llm-judge", action="store_true",
                        help="When using logprob_elbo, also compute LLM judge reward for comparison")

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
    parser.add_argument("--sampler-ttl-seconds", type=int, default=60,
                        help="TTL in seconds for sampler checkpoints (default: 60, use 0 for no expiry)")

    args = parser.parse_args()

    # Create overlay FIRST — before torch/transformers/PIL are loaded.
    overlay = None
    if not args.disable_inference and not args.no_overlay:
        overlay = ActionOverlay()

    # Now safe to import heavy modules (torch, transformers, tinker, etc.)
    from powernap.longnap.trainer import OnlineEnvTrainer
    from powernap.napsack.pipeline import label_loop
    from powernap.inference.loop import inference_loop
    from powernap.napsack import OnlineRecorder, Labeler
    from powernap.inference import Predictor
    from powernap.sleepwalk import SleepWalker
    from transformers import AutoTokenizer
    from record.constants import constants_manager

    try:
        import wandb
    except ImportError:
        wandb = None

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Setup precision preset
    constants_manager.set_preset(args.precision, verbose=False)

    # Tokenizer (for inference)
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)

    # Stage 1: Recorder
    # Handle --disable-events: None means use default, [] means enable all
    disable_events = args.disable_events
    if disable_events is not None and len(disable_events) == 0:
        disable_events = []  # Explicitly enable all events
    
    recorder = OnlineRecorder(
        fps=args.fps,
        buffer_seconds=args.buffer_seconds,
        log_dir=args.log_dir,
        save_screenshots=args.save_screenshots,
        disable=disable_events,
    )

    # Stage 2: Labeler (video chunk-based)
    labeler = Labeler(
        chunk_size=args.chunk_size,
        fps=args.chunk_fps,
        max_workers=args.chunk_workers,
        log_dir=recorder.session_dir,
    )

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
        sampler_ttl_seconds=args.sampler_ttl_seconds or None,
        loss_mode=args.loss_mode,
        eval_with_llm_judge=args.eval_with_llm_judge,
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
    shutdown_event = threading.Event()

    def shutdown(sig, frame):
        if shutdown_event.is_set():
            # Second Ctrl+C — force exit immediately
            print("\n[shutdown] forced exit")
            os._exit(1)
        print("\n[shutdown] shutting down...")
        shutdown_event.set()
        recorder.stop()
        if overlay:
            overlay.close()

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
            kwargs={"num_imgs_per_sample": args.num_imgs_per_sample},
            daemon=True,
        )
        inference_thread.start()

    # sleepwalk thread
    sleepwalk_thread = threading.Thread(target=walker.run, daemon=True)
    sleepwalk_thread.start()

    # Training loop (runs on background thread)
    def train_loop():
        trainer.run_streaming(
            recorder=recorder,
            label_queue=label_queue,
            past_len=args.past_len,
            future_len=args.future_len,
            batch_size=args.batch_size,
            num_imgs_per_sample=args.num_imgs_per_sample,
            shutdown_event=shutdown_event,
        )

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

    # Cleanup
    shutdown_event.set()
    recorder.stop()
    train_thread.join(timeout=5)

    if args.log_to_wandb:
        try:
            if wandb and wandb.run is not None:
                wandb.finish()
        except Exception:
            pass

    print("[shutdown] done")


if __name__ == "__main__":
    main()

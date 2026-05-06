#!/usr/bin/env python3
"""Uvicorn launcher for the Tada FastAPI server."""

import argparse
import logging
import os
import threading
import time
import signal
import uvicorn


logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")


def _watch_parent():
    """Exit if parent process dies (re-parented to PID 1 / launchd)."""
    ppid = os.getppid()
    while True:
        time.sleep(2)
        if os.getppid() != ppid:
            logging.getLogger(__name__).info("Parent process died, shutting down")
            os.kill(os.getpid(), signal.SIGTERM)
            time.sleep(5)
            logging.getLogger(__name__).warning("Parent process is gone; forcing server exit")
            os._exit(143)
            break


def main():
    parser = argparse.ArgumentParser(description="Tada FastAPI server")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--save-recordings", action="store_true")
    parser.add_argument("--resume-from-checkpoint", type=str, default=None)
    parser.add_argument("--retriever-checkpoint", type=str, default=None)
    parser.add_argument("--log-dir", type=str, default="./logs",
                        help="Directory to save logs, checkpoints, and recordings")
    parser.add_argument("--loss-mode", type=str, default="llm_judge",
                        choices=["llm_judge", "logprob_elbo"],
                        help="Training loss mode (default: llm_judge)")
    parser.add_argument("--model-type", type=str, default="prompted",
                        choices=["powernap", "prompted"],
                        help="Predictor type: 'powernap' (finetuned, requires Tinker) or 'prompted' (LiteLLM baseline)")
    parser.add_argument("--google-token-path", type=str, default=None,
                        help="Path to Google OAuth token JSON file")
    parser.add_argument("--outlook-token-path", type=str, default=None,
                        help="Path to Outlook OAuth token JSON file")
    parser.add_argument("--log-to-wandb", action="store_true",
                        help="Enable Weights & Biases logging")
    parser.add_argument("--wandb-project", type=str, default="longnap-online")
    parser.add_argument("--wandb-run-name", type=str, default="longnap-online-env")
    args = parser.parse_args()

    if args.save_recordings:
        os.environ["TADA_SAVE_RECORDINGS"] = "1"
    if args.resume_from_checkpoint:
        os.environ["TADA_RESUME_FROM_CHECKPOINT"] = args.resume_from_checkpoint
    if args.retriever_checkpoint:
        os.environ["TADA_RETRIEVER_CHECKPOINT"] = args.retriever_checkpoint
    if args.google_token_path:
        os.environ["TADA_GOOGLE_TOKEN_PATH"] = args.google_token_path
    if args.outlook_token_path:
        os.environ["TADA_OUTLOOK_TOKEN_PATH"] = args.outlook_token_path
    os.environ["TADA_LOG_DIR"] = args.log_dir
    os.environ["TADA_LOSS_MODE"] = args.loss_mode
    os.environ["TADA_MODEL_TYPE"] = args.model_type
    if (args.log_to_wandb or os.environ.get("WANDB_API_KEY")) and os.environ.get("WANDB_API_KEY"):
        os.environ["TADA_LOG_TO_WANDB"] = "1"
    os.environ["TADA_WANDB_PROJECT"] = args.wandb_project
    os.environ["TADA_WANDB_RUN_NAME"] = args.wandb_run_name
    os.environ["TADA_PORT"] = str(args.port)

    threading.Thread(target=_watch_parent, daemon=True).start()

    uvicorn.run(
        "server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()

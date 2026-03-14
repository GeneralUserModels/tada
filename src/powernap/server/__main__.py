#!/usr/bin/env python3
"""Uvicorn launcher for the PowerNap FastAPI server."""

import argparse
import logging
import os
import uvicorn
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")


def main():
    parser = argparse.ArgumentParser(description="PowerNap FastAPI server")
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
    parser.add_argument("--gws-path", type=str, default=None,
                        help="Path to gws CLI binary")
    parser.add_argument("--log-to-wandb", action="store_true",
                        help="Enable Weights & Biases logging")
    parser.add_argument("--wandb-project", type=str, default="longnap-online")
    parser.add_argument("--wandb-run-name", type=str, default="longnap-online-env")
    args = parser.parse_args()

    if args.save_recordings:
        os.environ["POWERNAP_SAVE_RECORDINGS"] = "1"
    if args.resume_from_checkpoint:
        os.environ["POWERNAP_RESUME_FROM_CHECKPOINT"] = args.resume_from_checkpoint
    if args.retriever_checkpoint:
        os.environ["POWERNAP_RETRIEVER_CHECKPOINT"] = args.retriever_checkpoint
    if args.gws_path:
        os.environ["POWERNAP_GWS_PATH"] = args.gws_path
    os.environ["POWERNAP_LOG_DIR"] = args.log_dir
    os.environ["POWERNAP_LOSS_MODE"] = args.loss_mode
    if (args.log_to_wandb or os.environ.get("WANDB_API_KEY")) and os.environ.get("WANDB_API_KEY"):
        os.environ["POWERNAP_LOG_TO_WANDB"] = "1"
    os.environ["POWERNAP_WANDB_PROJECT"] = args.wandb_project
    os.environ["POWERNAP_WANDB_RUN_NAME"] = args.wandb_run_name

    uvicorn.run(
        "powernap.server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()

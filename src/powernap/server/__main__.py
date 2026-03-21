#!/usr/bin/env python3
"""Uvicorn launcher for the PowerNap FastAPI server."""

import argparse
import json
import logging
import os
from pathlib import Path
import uvicorn


def _load_config_env() -> None:
    """Load API keys from powernap-config.json (cwd = project root in dev)."""
    config_path = Path.cwd() / "powernap-config.json"
    if not config_path.exists():
        return
    try:
        data = json.loads(config_path.read_text())
    except Exception:
        return
    mapping = {
        "gemini_api_key": "GEMINI_API_KEY",
        "tinker_api_key": "TINKER_API_KEY",
        "wandb_api_key": "WANDB_API_KEY",
        "hf_token": "HF_TOKEN",
    }
    for key, env_var in mapping.items():
        if data.get(key) and not os.environ.get(env_var):
            os.environ[env_var] = data[key]


_load_config_env()

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
        os.environ["POWERNAP_SAVE_RECORDINGS"] = "1"
    if args.resume_from_checkpoint:
        os.environ["POWERNAP_RESUME_FROM_CHECKPOINT"] = args.resume_from_checkpoint
    if args.retriever_checkpoint:
        os.environ["POWERNAP_RETRIEVER_CHECKPOINT"] = args.retriever_checkpoint
    if args.google_token_path:
        os.environ["POWERNAP_GOOGLE_TOKEN_PATH"] = args.google_token_path
    if args.outlook_token_path:
        os.environ["POWERNAP_OUTLOOK_TOKEN_PATH"] = args.outlook_token_path
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

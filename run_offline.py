#!/usr/bin/env python3
"""
Training script for LongNAP using Tinker's RL training infrastructure.

Uses the Env abstraction from tinker_cookbook for cleaner multi-turn RL training.
"""

from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
from datetime import datetime

import chz

from tinker_cookbook import cli_utils
from tinker_cookbook.rl import train

from powernap.longnap.dataset import LongNAPDatasetBuilder


@chz.chz
class CLIConfig:
    """Command-line configuration for LongNAP training."""
    
    # Model configuration
    model_name: str = "Qwen/Qwen3-VL-30B-A3B-Instruct"
    renderer_name: str | None = None
    
    # Dataset configuration
    dataset_path: str = "./train-00000-of-00001.parquet"
    past_len: int = 8
    future_len: int = 4
    stride: int = 4
    num_imgs_per_sample: int = 0
    include_timestamps: bool = False
    
    # Training configuration
    batch_size: int = 2
    group_size: int = 8
    learning_rate: float = 1e-5
    max_tokens: int = 512
    temperature: float = 1.0
    lora_rank: int = 32
    
    # Retrieval configuration
    retrieval_top_k: int = 10
    retrieval_mmr_k: int = 10
    retrieval_mmr_alpha: float = 0.5
    retrieval_time_decay_lambda: float = 0.5
    dedup_threshold: float = 0.8
    
    # Reward configuration
    reward_llm: str = "gemini/gemini-3-flash-preview"

    # Loss mode
    loss_mode: str = "llm_judge"           # "llm_judge" or "logprob_elbo"
    eval_with_llm_judge: bool = False      # when using logprob_elbo, also compute LLM judge reward

    # Logging and checkpointing
    log_path: str | None = None
    wandb_project: str | None = None
    wandb_name: str | None = None
    eval_every: int = 20
    save_every: int = 20
    num_groups_to_log: int = 4
    sampler_ttl_seconds: int | None = 60


def build_config(cli_config: CLIConfig) -> train.Config:
    """
    Build a train.Config from CLI arguments.
    
    Args:
        cli_config: Parsed CLI configuration
        
    Returns:
        A train.Config for the training loop
    """
    # Generate run name and log path
    date_and_time = datetime.now().strftime("%Y-%m-%d-%H-%M")
    model_short = cli_config.model_name.split("/")[-1]
    run_name = f"longnap-{model_short}-{cli_config.group_size}g-{cli_config.batch_size}b-{date_and_time}"
    
    if cli_config.log_path is not None:
        log_path = cli_config.log_path
    else:
        log_path = f"/tmp/longnap/{run_name}"
    
    if cli_config.wandb_name is not None:
        wandb_name = cli_config.wandb_name
    else:
        wandb_name = run_name
    
    # Build reward scorer override for ELBO mode (skip LLM judge when not needed)
    reward_scorer = None
    if cli_config.loss_mode == "logprob_elbo" and not cli_config.eval_with_llm_judge:
        async def _dummy_scorer(actions, ground_truth):
            return 0.0
        reward_scorer = _dummy_scorer

    # Build dataset builder
    dataset_builder = LongNAPDatasetBuilder(
        model_name=cli_config.model_name,
        renderer_name=cli_config.renderer_name,
        dataset_path=cli_config.dataset_path,
        past_len=cli_config.past_len,
        future_len=cli_config.future_len,
        stride=cli_config.stride,
        num_imgs_per_sample=cli_config.num_imgs_per_sample,
        include_timestamps=cli_config.include_timestamps,
        batch_size=cli_config.batch_size,
        group_size=cli_config.group_size,
        retrieval_top_k=cli_config.retrieval_top_k,
        retrieval_mmr_k=cli_config.retrieval_mmr_k,
        retrieval_mmr_alpha=cli_config.retrieval_mmr_alpha,
        retrieval_time_decay_lambda=cli_config.retrieval_time_decay_lambda,
        dedup_threshold=cli_config.dedup_threshold,
        reward_llm=cli_config.reward_llm,
        reward_scorer=reward_scorer,
    )
    
    # Build train config
    return train.Config(
        model_name=cli_config.model_name,
        log_path=log_path,
        dataset_builder=dataset_builder,
        learning_rate=cli_config.learning_rate,
        max_tokens=cli_config.max_tokens,
        temperature=cli_config.temperature,
        lora_rank=cli_config.lora_rank,
        eval_every=cli_config.eval_every,
        save_every=cli_config.save_every,
        wandb_project=cli_config.wandb_project,
        wandb_name=wandb_name,
        num_groups_to_log=cli_config.num_groups_to_log,
        ttl_seconds=cli_config.sampler_ttl_seconds,
    )


def main():
    """Main entry point for LongNAP training."""
    cli_config = chz.entrypoint(CLIConfig)
    config = build_config(cli_config)
    
    # Check if log dir exists and ask user what to do
    cli_utils.check_log_dir(config.log_path, behavior_if_exists="ask")
    
    # Run the training loop
    if cli_config.loss_mode == "logprob_elbo":
        from powernap.longnap.elbo import main_elbo
        asyncio.run(main_elbo(config, cli_config.eval_with_llm_judge))
    else:
        asyncio.run(train.main(config))


if __name__ == "__main__":
    main()

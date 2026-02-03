#!/usr/bin/env bash
set -e

# LongNAP Offline Training Pipeline
# Trains on a pre-recorded parquet dataset using Env-based RL
# Make sure .env is configured with GEMINI_API_KEY and TINKER_API_KEY

uv run run_offline.py \
    model_name=Qwen/Qwen3-VL-30B-A3B-Instruct \
    dataset_path=train-00000-of-00001.parquet \
    past_len=16 \
    future_len=8 \
    stride=4 \
    num_imgs_per_sample=2 \
    batch_size=2 \
    group_size=8 \
    learning_rate=1e-5 \
    max_tokens=512 \
    temperature=1.0 \
    lora_rank=32 \
    retrieval_top_k=10 \
    retrieval_mmr_k=10 \
    retrieval_mmr_alpha=0.5 \
    retrieval_time_decay_lambda=0.5 \
    dedup_threshold=0.8 \
    reward_llm=gemini/gemini-3-flash-preview \
    eval_every=20 \
    save_every=20 \
    num_groups_to_log=4 \
    wandb_project=longnap-offline \
    wandb_name="${USER:-longnap}-$(date +%Y%m%d-%H%M%S)"

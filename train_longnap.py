#!/usr/bin/env python3
"""
Simple training script for LongNAP using Tinker.
"""

import argparse
from datasets import load_dataset
from transformers import AutoTokenizer

from powernap.longnap.trainer import LongNAP
from powernap.longnap.dataset import NAPSack


def main():
    parser = argparse.ArgumentParser(description="Train LongNAP model")
    parser.add_argument("--dataset_path", type=str, default="./train-00000-of-00001.parquet", help="Path to parquet dataset")
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-VL-30B-A3B-Instruct")
    parser.add_argument("--reward_llm", type=str, default="gemini/gemini-3-flash-preview")
    parser.add_argument("--num_generations", type=int, default=8)
    parser.add_argument("--learning_rate", type=float, default=1e-5)
    parser.add_argument("--max_completion_length", type=int, default=512)
    parser.add_argument("--past_len", type=int, default=8)
    parser.add_argument("--future_len", type=int, default=4)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--num_steps", type=int, default=10)
    parser.add_argument("--log_every_n_steps", type=int, default=1)
    parser.add_argument("--log_dir", type=str, default="./logs")
    parser.add_argument("--log_to_wandb", action="store_true")
    parser.add_argument("--wandb_project", type=str, default="longnap")
    parser.add_argument("--wandb_run_name", type=str, default="longnap-run")
    args = parser.parse_args()

    # Load tokenizer for chat template
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)

    # Load dataset
    raw_dataset = load_dataset("parquet", data_files=args.dataset_path)

    train_dataset = NAPSack(
        raw_dataset=raw_dataset,
        past_len=args.past_len,
        future_len=args.future_len,
        stride=args.stride,
        split="train",
        processor=tokenizer,
    )

    # Initialize trainer
    trainer = LongNAP(
        model=args.model,
        train_dataset=train_dataset,
        reward_llm=args.reward_llm,
        num_generations=args.num_generations,
        learning_rate=args.learning_rate,
        max_completion_length=args.max_completion_length,
        generation_batch_size=args.batch_size,
        log_every_n_steps=args.log_every_n_steps,
        log_dir=args.log_dir,
        log_to_wandb=args.log_to_wandb,
        wandb_project=args.wandb_project,
        wandb_run_name=args.wandb_run_name,
    )

    # Create data iterator
    def data_iter():
        for step in range(args.num_steps):
            batch = []
            for _ in range(args.batch_size):
                idx = step * args.batch_size + len(batch)
                idx = idx % len(train_dataset)
                batch.append(train_dataset[idx])
            yield batch

    # Train
    trainer.train(data_iter())


if __name__ == "__main__":
    main()

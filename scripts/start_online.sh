#!/usr/bin/env bash
set -e

# LongNAP Online Pipeline
# Records screen → labels with LLM → trains with Env-based RL → predicts next actions
# Make sure .env is configured with GEMINI_API_KEY and TINKER_API_KEY

uv run_online.py \                                                                
    --fps 5 --checkpoint-every-n-steps 20\
    --buffer-seconds 120 \
    --precision accurate \
    --label-model gemini/gemini-3-flash-preview \
    --model Qwen/Qwen3-VL-30B-A3B-Instruct \
    --reward-llm gemini/gemini-3-flash-preview \
    --num-imgs-per-sample 2 \
    --num-generations 8 \
    --learning-rate 1e-5 \
    --max-completion-length 512 \
    --past-len 16 \
    --future-len 8 \
    --batch-size 8 \
    --predict-every-n-seconds 10 \
    --log-every-n-steps 1 \
    --log-dir ./logs \
    --log-to-wandb \
    --wandb-project longnap-online \
    --wandb-run-name "${USER:-longnap}-$(date +%Y%m%d-%H%M%S)" \
    --checkpoint-every-n-steps 10 \
    --resume-from-checkpoint auto
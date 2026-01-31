# PowerNap

Online record → label → train → infer pipeline for user action prediction.

## Install

```bash
cd powernap

# clone and install pack into this directory
git clone git@github.com:GeneralUserModels/pack.git
cd pack && uv pip install -e .

# clone tinker-cookbook into this directory
git clone https://github.com/thinking-machines-lab/tinker-cookbook.git
cd tinker-cookbook && uv pip install -e .

# install (pack + tinker + tinker-cookbook are resolved automatically via uv)
uv pip install -e ".[wandb]"
```

## Environment

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

Required variables:

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | for litellm labeling & reward model |
| `TINKER_API_KEY` | for tinker OAI inference endpoint |
| `WANDB_API_KEY` | (optional) for wandb logging |

The entry scripts (`train_longnap.py`, `run_inference.py`, `run_online.py`) automatically load `.env` via `python-dotenv`.

> **Note:** tinker service must be running for training + inference

## Modules

- **`powernap.napsack`** — online data recording + labeling
  - `OnlineRecorder` — screen & input capture (wraps pack's recorder, streams aggregations via queue)
  - `Labeler` — labels aggregations with litellm (screenshot + events → action caption)

- **`powernap.longnap`** — training
  - `LongNAP` — think → retrieve → revise → actions trainer (tinker + litellm reward)
  - `NAPSack` — sliding-window dataset over labeled action sequences

- **`powernap.inference`** — inference
  - `Predictor` — think → retrieve → revise → actions prediction via tinker OAI endpoint
  - `ActionOverlay` — macOS transparent overlay showing predicted next actions

## Online Pipeline

`run_online.py` wires all four stages concurrently:

```
[Recorder threads]  →  aggregation_queue  →  [Label thread]  →  label_queue  →  [Train thread]
   (pynput/mss)                               (litellm)         │                 (tinker)
                                                                 │
                                                                 └→ inference_buffer → [Inference thread]
                                                                                        (tinker OAI)
                                                                                            │
                                                                                        [Overlay]
                                                                                        (AppKit)
```

- Labels feed both training (via `label_queue`) and inference (via `inference_buffer`)
- Inference picks up new checkpoints from the trainer automatically
- Predictions are evaluated against ground truth labels as they arrive (delayed scoring with LLM judge)
- macOS overlay shows predicted next actions in real time

### Training & Gradient Accumulation

The training loop uses **streaming micro-batch gradient accumulation**. Each labeled sample is processed immediately as it arrives — no waiting for a full batch:

1. A new record arrives from `label_queue`
2. Once enough context is buffered (`past_len + future_len` records), a sample is created
3. The sample is immediately rolled out (GRPO with `num_generations` completions) and `forward_backward` is called (micro-batch = 1)
4. Tinker accumulates gradients across `forward_backward` calls
5. After `batch_size` micro-batches, a single `optim_step` applies the accumulated gradients and the sampler weights are updated

This means training starts as soon as data is available, rather than waiting for an entire batch to fill up. The `--batch-size` flag controls how many micro-batches of gradients accumulate before each optimizer step. All micro-batches within a step use the same policy weights for rollouts (the sampler is only updated after `optim_step`).

Advantages are computed per-group (GRPO-style normalization), and the logged loss is the mean across micro-batches in the step.

### Shutdown

Press **Ctrl+C** to shut down gracefully. The signal handler stops the recorder, closes the overlay, and lets threads exit cleanly. Press **Ctrl+C a second time** to force an immediate exit.

### Run

```bash
uv run run_online.py
```

With options:

```bash
uv run run_online.py \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct \
  --label-model gemini/gemini-2.0-flash \
  --reward-llm gemini/gemini-3-flash-preview \
  --num-generations 8 \
  --learning-rate 1e-5 \
  --past-len 8 --future-len 4 --batch-size 2 \
  --num-imgs-per-sample 2 \
  --predict-every-n-seconds 10 \
  --log-dir ./logs --log-to-wandb --wandb-project longnap-online
```

| Flag | Default | Description |
|------|---------|-------------|
| `--model` | `Qwen/Qwen3-VL-30B-A3B-Instruct` | Base model for training & sampling |
| `--label-model` | `gemini/gemini-2.0-flash` | LLM for labeling screen recordings |
| `--reward-llm` | `gemini/gemini-3-flash-preview` | LLM judge for reward scoring |
| `--num-generations` | `8` | Rollouts per sample (GRPO group size) |
| `--learning-rate` | `1e-5` | Adam learning rate |
| `--max-completion-length` | `512` | Max tokens per rollout completion |
| `--num-imgs-per-sample` | `2` | Screenshots per sample (0 = text only) |
| `--past-len` | `8` | Context actions in each sample |
| `--future-len` | `4` | Ground-truth actions to predict |
| `--batch-size` | `2` | Micro-batches accumulated per optimizer step |
| `--predict-every-n-seconds` | `10` | Inference polling interval |
| `--disable-inference` | off | Skip inference thread entirely |
| `--no-overlay` | off | Run inference without macOS overlay |
| `--checkpoint-every-n-steps` | `0` | Save checkpoint every N steps (0 = disabled) |
| `--resume-from-checkpoint` | none | Path or `auto` to resume from latest |

### Inference Only

`run_inference.py` runs recording + labeling + inference without training, using a fixed checkpoint:

```bash
uv run run_inference.py \
  --model-path "tinker://uuid:train:0/sampler_weights/000080" \
  --tokenizer Qwen/Qwen3-VL-30B-A3B-Instruct \
  --past-len 8 --future-len 4
```

### Offline Training

```bash
python train_longnap.py --dataset_path ./train-00000-of-00001.parquet
```

## Output

All data saved to `--log-dir` (default `./logs`):

```
logs/session_YYYYMMDD_HHMMSS/
├── screenshots/           # JPEGs from recorder
├── raw_aggregations.jsonl # event burst aggregations
├── input_events.jsonl     # raw mouse/keyboard events
├── screenshots.jsonl      # screenshot metadata
├── labels.jsonl           # litellm action captions
└── predictions.jsonl      # inference predictions (think, revise, actions)
```

## wandb

Pass `--log-to-wandb` to log pipeline, training, and inference metrics:

| Metric | Description |
|--------|-------------|
| `pipeline/labels_total` | cumulative labels produced |
| `pipeline/label_latency_s` | seconds per litellm call |
| `pipeline/label_image` | screenshot + caption (every 10th) |
| `pipeline/buffer_size` | labeled records in buffer |
| `pipeline/batches_yielded` | optimizer steps completed |
| `train/step` | current training step |
| `train/loss` | mean loss across micro-batches in step |
| `train/reward_mean` | mean reward across all trajectories in step |
| `train/reward_std` | reward standard deviation |
| `train/num_trajectories` | total trajectories in step |
| `train/step_time` | wall-clock seconds for the step |
| `train/retriever_size` | documents in the BM25 retriever |
| `inference/predictions_total` | cumulative predictions made |
| `inference/reward` | LLM judge score (0-1) for prediction vs ground truth |
| `inference/evals_total` | cumulative evaluations completed |

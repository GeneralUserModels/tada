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

### Run

```bash
uv run run_online.py
```

With options:

```bash
uv run run_online.py \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct \
  --label-model gemini/gemini-3-flash-preview \
  --reward-llm gemini/gemini-3-flash-preview \
  --past-len 8 --future-len 4 --batch-size 2 \
  --predict-every-n-seconds 10 \
  --log-dir ./logs --log-to-wandb --wandb-project longnap-online
```

Use `--disable-inference` to skip the inference thread, or `--no-overlay` to run inference without the screen overlay.

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
| `pipeline/batches_yielded` | batches sent to trainer |
| `loss`, `reward_mean`, ... | training metrics (from LongNAP) |
| `inference/predictions_total` | cumulative predictions made |
| `inference/latency_s` | seconds per prediction |
| `inference/reward` | LLM judge score (0-1) for prediction vs ground truth |
| `inference/evals_total` | cumulative evaluations completed |
| `inference/eval` | table with think, revise, actions, ground truth, reward |

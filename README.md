# PowerNap

Online record → label → train pipeline for user action prediction.

## Install

```bash
# install pack (recording backend) first
cd ../pack && uv pip install -e .

# install powernap
cd ../powernap && uv pip install -e ".[wandb]"
```

## Environment

```bash
export GEMINI_API_KEY=...   # for litellm labeling & reward model
# tinker service must be running for training
```

## Modules

- **`powernap.napsack`** — online data recording + labeling
  - `OnlineRecorder` — screen & input capture (wraps pack's recorder, streams aggregations via queue)
  - `Labeler` — labels aggregations with litellm (screenshot + events → action caption)

- **`powernap.longnap`** — training
  - `LongNAP` — think → retrieve → revise → actions trainer (tinker + litellm reward)
  - `NAPSack` — sliding-window dataset over labeled action sequences

## Online Pipeline

`run_online.py` wires all three stages concurrently:

```
[Recorder threads]  →  aggregation_queue  →  [Label thread]  →  label_queue  →  [Trainer]
   (pynput/mss)                               (litellm)                         (tinker)
```

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
  --log-dir ./logs --log-to-wandb --wandb-project longnap-online
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
└── labels.jsonl           # litellm action captions
```

## wandb

Pass `--log-to-wandb` to log both pipeline and training metrics:

| Metric | Description |
|--------|-------------|
| `pipeline/labels_total` | cumulative labels produced |
| `pipeline/label_latency_s` | seconds per litellm call |
| `pipeline/label_image` | screenshot + caption (every 10th) |
| `pipeline/buffer_size` | labeled records in buffer |
| `pipeline/batches_yielded` | batches sent to trainer |
| `loss`, `reward_mean`, ... | training metrics (from LongNAP) |

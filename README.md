# PowerNap

Online record → label → train → infer pipeline for user action prediction.

## Install

```bash
cd powernap
npm run install:electron
```

## Environment

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | for litellm labeling & reward model |
| `TINKER_API_KEY` | for tinker OAI inference endpoint |
| `WANDB_API_KEY` | (optional) for wandb logging |

> **Note:** tinker service must be running for training + inference

## Run

```bash
npm run dev
```

The desktop app starts the Python server automatically and opens the dashboard. Use **Ctrl+H** to toggle the prediction overlay.

## Output

All data saved to `logs-app/session_YYYYMMDD_HHMMSS/`:

```
├── screenshots/           # JPEGs from recorder
├── raw_aggregations.jsonl # event burst aggregations
├── input_events.jsonl     # raw mouse/keyboard events
├── screenshots.jsonl      # screenshot metadata
├── labels.jsonl           # litellm action captions
└── predictions.jsonl      # inference predictions (think, revise, actions)
```

## Advanced: headless server

To run the pipeline without the desktop app:

```bash
uv run run_server.py
```

With options:

```bash
uv run run_server.py \
  --port 8000 \
  --log-dir ./logs \
  --save-recordings \
  --resume-from-checkpoint auto \
  --loss-mode llm_judge \
  --log-to-wandb --wandb-project longnap-online
```

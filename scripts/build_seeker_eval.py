"""
Build a parquet dataset for evaluating seeker conversation impact.

Each row is a next-action prediction task created from a sliding window over
a day's events. Contains the past actions context, ground truth, and any
applicable seeker conversations — everything needed to run vanilla vs.
seeker-augmented predictions.

Usage:
    uv run python scripts/build_seeker_eval.py [--log-dir ./logs] [--date 2026-04-14] [--num-samples 25]
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from user_models.powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION, build_actions_block, collect_dense_captions,
)

import pandas as pd


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_events(log_dir: Path, target_date: str) -> list[dict]:
    all_events = []
    for jsonl_path in sorted(log_dir.glob("*/filtered.jsonl")):
        connector = jsonl_path.parent.name
        if connector == "active-conversations":
            continue
        for line in jsonl_path.read_text().splitlines():
            if not line.strip():
                continue
            raw = json.loads(line)
            all_events.append({
                "timestamp": raw["timestamp"],
                "text": raw.get("text", ""),
                "dense_caption": raw.get("dense_caption", ""),
                "source_name": raw.get("source_name", connector),
                "prediction_event": bool(raw.get("prediction_event", False)),
                "img_path": raw.get("img_path"),
            })
    all_events.sort(key=lambda e: e["timestamp"])
    return [
        e for e in all_events
        if datetime.fromtimestamp(e["timestamp"]).strftime("%Y-%m-%d") == target_date
    ]


def load_seeker_conversations(log_dir: Path) -> list[dict]:
    conversations_dir = log_dir / "active-conversations"
    conversations = []
    for md_path in sorted(conversations_dir.glob("conversation_*.md")):
        stem = md_path.stem
        parts = stem.split("_")
        dt = datetime.strptime(f"{parts[1]}_{parts[2]}", "%Y%m%d_%H%M%S")
        text = md_path.read_text().replace("# Conversation\n\n", "").strip()
        conversations.append({
            "timestamp": dt.timestamp(),
            "text": text,
            "filename": md_path.name,
        })
    return conversations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Build seeker eval parquet dataset")
    parser.add_argument("--log-dir", default="./logs")
    parser.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--past-len", type=int, default=None)
    parser.add_argument("--future-len", type=int, default=None)
    parser.add_argument("--num-samples", type=int, default=256)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    log_dir = Path(args.log_dir).resolve()

    # Read config for defaults
    config = json.loads(Path("powernap-config.json").read_text())
    past_len = args.past_len or config.get("past_len", 16)
    future_len = args.future_len or config.get("future_len", 8)
    output_path = Path(args.output) if args.output else log_dir / "seeker_eval.parquet"

    # Load events
    print(f"Loading events for {args.date} from {log_dir}...")
    events = load_events(log_dir, args.date)
    predict_events = [e for e in events if e.get("prediction_event")]
    print(f"  Total events: {len(events)}, prediction events: {len(predict_events)}")

    # Load seeker conversations
    conversations = load_seeker_conversations(log_dir)
    print(f"  Seeker conversations: {len(conversations)}")
    for c in conversations:
        print(f"    {datetime.fromtimestamp(c['timestamp']).strftime('%H:%M:%S')} — {c['filename']}")

    # Create sliding window samples
    min_buffer = past_len + future_len
    assert len(predict_events) >= min_buffer, (
        f"Need at least {min_buffer} prediction events, got {len(predict_events)}"
    )
    max_start = len(predict_events) - min_buffer
    if args.num_samples >= max_start + 1:
        positions = list(range(max_start + 1))
    else:
        step = max_start / (args.num_samples - 1)
        positions = [round(i * step) for i in range(args.num_samples)]

    print(f"  Creating {len(positions)} samples (past_len={past_len}, future_len={future_len})")

    rows = []
    for i, pos in enumerate(positions):
        past = predict_events[pos : pos + past_len]
        future = predict_events[pos + past_len : pos + past_len + future_len]
        boundary_ts = past[-1]["timestamp"]

        past_actions_block = build_actions_block(past, include_descriptions=True)
        ground_truth = build_actions_block(future)
        dense_caption = collect_dense_captions(past)

        # Include all seeker conversations for every sample
        seeker_text = "\n\n---\n\n".join(c["text"] for c in conversations) if conversations else ""

        rows.append({
            "sample_idx": i,
            "boundary_ts": boundary_ts,
            "boundary_time": datetime.fromtimestamp(boundary_ts).strftime("%H:%M:%S"),
            "past_len": past_len,
            "future_len": future_len,
            "past_actions": past_actions_block,
            "ground_truth": ground_truth,
            "dense_caption": dense_caption,
            "num_seeker_convos": len(conversations),
            "seeker_text": seeker_text,
            "task_description": TASK_DESCRIPTION,
        })

    df = pd.DataFrame(rows)
    df.to_parquet(output_path, index=False)

    print(f"\nSaved {len(df)} samples to {output_path}")
    print(f"  Pre-seeker (no convos):  {len(df[df['num_seeker_convos'] == 0])}")
    print(f"  Post-seeker (has convos): {len(df[df['num_seeker_convos'] > 0])}")
    print(f"\nColumns: {list(df.columns)}")


if __name__ == "__main__":
    main()

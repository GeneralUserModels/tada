#!/usr/bin/env python3
"""Convert labels.jsonl + screenshots to parquet for offline training.

Usage:
    python scripts/convert_labels_to_parquet.py ./logs
    python scripts/convert_labels_to_parquet.py ./logs output.parquet

Combines all session_* directories in the log folder into a single parquet.
"""

import io
import json
import pandas as pd
from pathlib import Path
from PIL import Image


def image_to_bytes(img: Image.Image) -> bytes:
    """Convert PIL Image to PNG bytes for parquet storage."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def convert_labels_to_parquet(log_dir: str, output_path: str = None):
    log_path = Path(log_dir)

    # Find all session directories
    session_dirs = sorted([d for d in log_path.iterdir() if d.is_dir() and d.name.startswith("session_")])

    if not session_dirs:
        # Maybe log_dir is a single session
        if (log_path / "labels.jsonl").exists():
            session_dirs = [log_path]
        else:
            raise FileNotFoundError(f"No session directories or labels.jsonl found in {log_dir}")

    print(f"Found {len(session_dirs)} session(s)")

    all_rows = []
    for session_dir in session_dirs:
        labels_file = session_dir / "labels.jsonl"
        if not labels_file.exists():
            print(f"  Skipping {session_dir.name} (no labels.jsonl)")
            continue

        session_rows = 0
        with open(labels_file) as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)

                # Load image and convert to bytes for parquet
                img_bytes = None
                if row.get("screenshot_path"):
                    img_path = Path(row["screenshot_path"])
                    if img_path.exists():
                        img = Image.open(img_path)
                        img_bytes = image_to_bytes(img)

                all_rows.append({
                    "text": row.get("text", ""),
                    "start_time": row.get("start_time", ""),
                    "img": img_bytes,
                })
                session_rows += 1

        print(f"  {session_dir.name}: {session_rows} labels")

    if not all_rows:
        raise ValueError("No labels found in any session")

    print(f"Total: {len(all_rows)} labels")

    # Create DataFrame
    df = pd.DataFrame(all_rows)

    # Default output path
    if output_path is None:
        output_path = log_path / "train-00000-of-00001.parquet"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(output_path)
    print(f"Saved to {output_path}")

    return str(output_path)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python convert_labels_to_parquet.py <log_dir> [output.parquet]")
        print("Example: python convert_labels_to_parquet.py ./logs")
        sys.exit(1)

    log_dir = sys.argv[1]
    output = sys.argv[2] if len(sys.argv) > 2 else None
    convert_labels_to_parquet(log_dir, output)

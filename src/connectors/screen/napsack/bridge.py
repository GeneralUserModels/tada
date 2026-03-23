#!/usr/bin/env python3
"""Recording bridge: runs OnlineRecorder and outputs serialized aggregations as JSON lines to stdout.

The Electron client spawns this as a child process, reads stdout line-by-line,
and POSTs each aggregation to POST /api/recordings/aggregation.
"""

import json
import os
from pathlib import Path


def _load_config_env() -> None:
    """Load API keys from powernap-config.json."""
    env_path = os.environ.get("POWERNAP_CONFIG_PATH")
    config_path = Path(env_path) if env_path else Path.cwd() / "powernap-config.json"
    if not config_path.exists():
        return
    try:
        data = json.loads(config_path.read_text())
    except Exception:
        return
    mapping = {
        "gemini_api_key": "GEMINI_API_KEY",
        "tinker_api_key": "TINKER_API_KEY",
        "wandb_api_key": "WANDB_API_KEY",
        "hf_token": "HF_TOKEN",
    }
    for key, env_var in mapping.items():
        if data.get(key) and not os.environ.get(env_var):
            os.environ[env_var] = data[key]


_load_config_env()

import argparse
import base64
import io
import signal
import sys

from PIL import Image


def serialize_aggregation(processed_agg) -> str:
    """Convert a ProcessedAggregation to a JSON line."""
    req = processed_agg.request

    # Encode screenshot as base64 PNG
    screenshot_b64 = None
    if processed_agg.screenshot is not None:
        img = Image.fromarray(processed_agg.screenshot.data)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        screenshot_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    data = {
        "screenshot_b64": screenshot_b64,
        "events": processed_agg.events,
        "timestamp": req.timestamp,
        "end_timestamp": req.end_timestamp,
        "reason": req.reason,
        "event_type": req.event_type,
        "request_state": req.request_state,
        "screenshot_timestamp": req.screenshot_timestamp,
        "end_screenshot_timestamp": req.end_screenshot_timestamp if req.end_screenshot_timestamp is not None else 0.0,
        "monitor": {},
        "burst_id": str(getattr(req, "burst_id", "")),
        "scale_factor": getattr(req, "scale_factor", 1.0),
    }

    return json.dumps(data)


def main():
    parser = argparse.ArgumentParser(description="PowerNap recording bridge")
    parser.add_argument("--fps", type=int, default=5)
    parser.add_argument("--buffer-seconds", type=int, default=12)
    parser.add_argument("--precision", type=str, choices=["accurate", "rough"], default="accurate")
    parser.add_argument("--disable-events", type=str, nargs="*", default=None)
    args = parser.parse_args()

    from napsack.record.constants import constants_manager
    from . import OnlineRecorder

    os.environ["CAPTURE_PRECISION"] = args.precision
    constants_manager.set_preset()

    disable_events = args.disable_events
    if disable_events is not None and len(disable_events) == 0:
        disable_events = []

    recorder = OnlineRecorder(
        fps=args.fps,
        buffer_seconds=args.buffer_seconds,
        disable=disable_events,
    )

    def shutdown(sig, frame):
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Preload HIServices on main thread (macOS)
    try:
        import HIServices
        HIServices.AXIsProcessTrusted()
    except Exception:
        pass

    recorder.start()

    try:
        for agg in recorder.iter_aggregations():
            line = serialize_aggregation(agg)
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()


if __name__ == "__main__":
    main()

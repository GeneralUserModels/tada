"""LLM cost tracking via litellm callbacks — logs per-app, per-model cost every 60s."""

import asyncio
import logging
import os
import threading
import time
from collections import defaultdict

import litellm
from litellm.integrations.custom_logger import CustomLogger

logger = logging.getLogger(__name__)


class CostTracker:
    """Thread-safe accumulator for LLM costs keyed by (app, model)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._costs: dict[tuple[str, str], dict] = defaultdict(
            lambda: {"cost": 0.0, "calls": 0, "input_tokens": 0, "output_tokens": 0}
        )
        self._start_time = time.time()

    def record(self, app: str, model: str, cost: float, input_tokens: int = 0, output_tokens: int = 0):
        with self._lock:
            entry = self._costs[(app, model)]
            entry["cost"] += cost
            entry["calls"] += 1
            entry["input_tokens"] += input_tokens
            entry["output_tokens"] += output_tokens

    def snapshot(self) -> tuple[dict, float]:
        """Return cumulative costs and total elapsed seconds."""
        with self._lock:
            snapshot = {k: dict(v) for k, v in self._costs.items()}
            elapsed = time.time() - self._start_time
        return snapshot, elapsed


class CostCallback(CustomLogger):
    """litellm callback that records costs into a CostTracker."""

    def __init__(self, tracker: CostTracker):
        super().__init__()
        self._tracker = tracker

    def log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._record(kwargs, response_obj)

    async def async_log_success_event(self, kwargs, response_obj, start_time, end_time):
        self._record(kwargs, response_obj)

    def _record(self, kwargs, response_obj):
        metadata = (kwargs.get("litellm_params") or {}).get("metadata") or {}
        app = metadata.get("app") or os.environ.get("TADA_COST_APP", "unknown")
        model = kwargs.get("model", "unknown")
        cost = kwargs.get("response_cost") or 0.0

        usage = getattr(response_obj, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0

        self._tracker.record(app, model, cost, input_tokens, output_tokens)


async def run_cost_logger(tracker: CostTracker, interval: int = 60):
    """Log cumulative cost summary every *interval* seconds."""
    while True:
        await asyncio.sleep(interval)
        snapshot, elapsed = tracker.snapshot()
        if not snapshot:
            continue

        by_app: dict[str, list] = defaultdict(list)
        total_cost = 0.0
        total_calls = 0
        for (app, model), stats in sorted(snapshot.items()):
            by_app[app].append((model, stats))
            total_cost += stats["cost"]
            total_calls += stats["calls"]

        lines = []
        for app, entries in sorted(by_app.items()):
            app_cost = sum(s["cost"] for _, s in entries)
            app_calls = sum(s["calls"] for _, s in entries)
            lines.append(f"  {app}: ${app_cost:.4f} ({app_calls} calls)")
            for model, stats in entries:
                lines.append(
                    f"    {model}: ${stats['cost']:.4f} "
                    f"({stats['calls']} calls, "
                    f"{stats['input_tokens']}in/{stats['output_tokens']}out)"
                )

        logger.info(
            "[cost] %.0fs — $%.4f total (%d calls)\n%s",
            elapsed, total_cost, total_calls, "\n".join(lines),
        )


def init_cost_tracking() -> CostTracker:
    """Create tracker, register litellm callback, return tracker."""
    tracker = CostTracker()
    callback = CostCallback(tracker)
    if not isinstance(litellm.callbacks, list):
        litellm.callbacks = []
    litellm.callbacks.append(callback)
    return tracker

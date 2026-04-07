#!/usr/bin/env python3
"""
Quick TTFT benchmark for prompt-prefix reuse vs cache-busted prompts.

This benchmark intentionally uses plain string messages (no cache_control blocks)
to avoid provider-adapter transformations that can distort results.

Per trial:
1) Warm the "reused prefix" arm once.
2) Run two measured calls in randomized order:
   - REUSED_PREFIX: same large prefix each trial (cache-likely)
   - BUSTED_PREFIX: same size, but unique prefix each call (cache-unlikely)

Environment:
  - MODEL (optional, default: gemini/gemini-3.1-flash-lite-preview)
  - LLM_API_KEY (optional if provider does not need it locally)
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
import uuid
from pathlib import Path
from typing import Any

_CONFIG_CANDIDATES = [
    Path("powernap-config.json"),
    Path(__file__).resolve().parent.parent / "powernap-config.json",
]


def _load_default_api_key() -> str:
    """Best-effort read of default_llm_api_key from powernap-config.json."""
    for p in _CONFIG_CANDIDATES:
        try:
            data = json.loads(p.read_text())
            key = data.get("default_llm_api_key", "")
            if key:
                return key
        except Exception:
            continue
    return ""


def _tokenish_text(n_tokens: int, prefix: str) -> str:
    """Create roughly token-proportional text for quick relative benchmarking."""
    if n_tokens <= 0:
        return ""
    return " ".join(f"{prefix}_{i % 1000}" for i in range(n_tokens))


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _bust_prefix_at_start(text: str) -> str:
    """Change the first token so prefix caching cannot match from position 0."""
    parts = text.split(" ", 1)
    replacement = f"bust{uuid.uuid4().hex[:8]}"
    if len(parts) == 1:
        return replacement
    return f"{replacement} {parts[1]}"


def run_call(
    *,
    model: str,
    api_key: str,
    static_prefix: str,
    dynamic_suffix: str,
    max_tokens: int,
    mode: str,
) -> dict:
    from litellm import completion

    nonce = uuid.uuid4().hex
    dynamic = f"{dynamic_suffix}\nnonce_{nonce}\nReturn exactly: OK"
    if mode == "anthropic_cache":
        # Anthropic prompt-caching path: cache only the large reusable prefix.
        content = [
            {
                "type": "text",
                "text": static_prefix,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": dynamic},
        ]
    else:
        content = f"{static_prefix}\n{dynamic}"

    t0 = time.perf_counter()
    ttft_ms = None
    first_chunk_ms = None
    prompt_tokens = None
    cached_tokens = None

    stream = completion(
        model=model,
        api_key=api_key or None,
        messages=[{"role": "user", "content": content}],
        stream=True,
        stream_options={"include_usage": True},
        temperature=0,
        max_tokens=max_tokens,
    )

    for chunk in stream:
        if first_chunk_ms is None:
            first_chunk_ms = (time.perf_counter() - t0) * 1000
        if ttft_ms is None and getattr(chunk, "choices", None):
            piece = chunk.choices[0].delta.content if chunk.choices else ""
            if piece:
                ttft_ms = (time.perf_counter() - t0) * 1000

        usage = getattr(chunk, "usage", None)
        if usage is not None:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = getattr(details, "cached_tokens", None) if details else None
            if cached_tokens is None:
                # Anthropic fields often surfaced this way in LiteLLM responses.
                cached_tokens = getattr(usage, "cache_read_input_tokens", None)

    return {
        "ttft_ms": _safe_float(ttft_ms),
        "first_chunk_ms": _safe_float(first_chunk_ms),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark TTFT for reused vs cache-busted prompt prefixes.")
    parser.add_argument("--model", default="gemini/gemini-3.1-flash-lite-preview")
    parser.add_argument("--api-key", default="", help="Falls back to default_llm_api_key from powernap-config.json.")
    parser.add_argument("--total-tokens", type=int, default=20000)
    parser.add_argument("--cached-tokens", type=int, default=15000)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument(
        "--mode",
        choices=["plain", "anthropic_cache"],
        default="plain",
        help="plain: no manual cache controls; anthropic_cache: explicit cache_control blocks.",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--burn-in", type=int, default=2, help="Unreported warmup trials before measurement.")
    parser.add_argument("--trim-frac", type=float, default=0.2, help="Trim fraction per side for trimmed mean.")
    args = parser.parse_args()

    try:
        import litellm  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing dependency: litellm. Run this with your project Python environment "
            "(for example via `uv run` if you use uv)."
        ) from exc

    if not args.api_key:
        args.api_key = _load_default_api_key()
        if args.api_key:
            print(f"Using default_llm_api_key from powernap-config.json (ends ...{args.api_key[-4:]})")
        else:
            print("Warning: no API key provided and none found in powernap-config.json.")

    if args.total_tokens < 1:
        raise SystemExit("--total-tokens must be >= 1")
    if args.cached_tokens < 0:
        raise SystemExit("--cached-tokens must be >= 0")
    if args.cached_tokens > args.total_tokens:
        raise SystemExit("--cached-tokens must be <= --total-tokens")
    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if args.burn_in < 0:
        raise SystemExit("--burn-in must be >= 0")
    if not (0.0 <= args.trim_frac < 0.5):
        raise SystemExit("--trim-frac must be in [0.0, 0.5)")

    static_prefix = _tokenish_text(args.cached_tokens, "cache")
    dynamic_suffix = _tokenish_text(args.total_tokens - args.cached_tokens, "tail")

    rng = random.Random(args.seed)
    reused_first = []
    busted_first = []
    reused_cached = []
    busted_cached = []

    def fmt(v: float | None) -> str:
        return f"{v:.1f}" if isinstance(v, (int, float)) else "n/a"

    def trimmed_mean(vals: list[float], frac: float) -> float:
        if not vals:
            return float("nan")
        xs = sorted(vals)
        k = int(len(xs) * frac)
        core = xs[k:len(xs) - k] if len(xs) - 2 * k > 0 else xs
        return statistics.mean(core)

    print(
        f"Model={args.model} | total_tokens~{args.total_tokens} | "
        f"cached_tokens~{args.cached_tokens} | runs={args.runs} | burn_in={args.burn_in} | seed={args.seed}"
    )

    # Burn-in: stabilize connection/runtime effects before measuring.
    for _ in range(args.burn_in):
        _ = run_call(
            model=args.model,
            api_key=args.api_key,
            static_prefix=static_prefix,
            dynamic_suffix=dynamic_suffix,
            max_tokens=args.max_tokens,
            mode=args.mode,
        )

    for i in range(args.runs):
        # Warm reused-prefix for this trial to increase chance of cache reuse.
        _ = run_call(
            model=args.model,
            api_key=args.api_key,
            static_prefix=static_prefix,
            dynamic_suffix=dynamic_suffix,
            max_tokens=args.max_tokens,
            mode=args.mode,
        )
        order = ["REUSED_PREFIX", "BUSTED_PREFIX"]
        rng.shuffle(order)
        trial = {}
        for arm in order:
            if arm == "REUSED_PREFIX":
                out = run_call(
                    model=args.model,
                    api_key=args.api_key,
                    static_prefix=static_prefix,
                    dynamic_suffix=dynamic_suffix,
                    max_tokens=args.max_tokens,
                    mode=args.mode,
                )
            else:
                out = run_call(
                    model=args.model,
                    api_key=args.api_key,
                    static_prefix=_bust_prefix_at_start(static_prefix),
                    dynamic_suffix=dynamic_suffix,
                    max_tokens=args.max_tokens,
                    mode=args.mode,
                )
            trial[arm] = out
            print(
                f"[{i + 1}] {arm:<13} first_chunk_ms={fmt(out['first_chunk_ms'])} "
                f"prompt={out['prompt_tokens']} cached={out['cached_tokens']}"
            )

        r = trial["REUSED_PREFIX"]
        b = trial["BUSTED_PREFIX"]
        if isinstance(r["first_chunk_ms"], (int, float)):
            reused_first.append(float(r["first_chunk_ms"]))
        if isinstance(b["first_chunk_ms"], (int, float)):
            busted_first.append(float(b["first_chunk_ms"]))
        if isinstance(r["cached_tokens"], (int, float)):
            reused_cached.append(float(r["cached_tokens"]))
        if isinstance(b["cached_tokens"], (int, float)):
            busted_cached.append(float(b["cached_tokens"]))

    print("\n=== Summary ===")
    if reused_first and busted_first:
        med_reused = statistics.median(reused_first)
        med_busted = statistics.median(busted_first)
        tmean_reused = trimmed_mean(reused_first, args.trim_frac)
        tmean_busted = trimmed_mean(busted_first, args.trim_frac)
        delta_med = med_busted - med_reused
        ratio_med = med_busted / med_reused if med_reused > 0 else float("inf")
        delta_tmean = tmean_busted - tmean_reused
        ratio_tmean = tmean_busted / tmean_reused if tmean_reused > 0 else float("inf")
        print(f"median REUSED first_chunk_ms: {med_reused:.1f}")
        print(f"median BUSTED first_chunk_ms: {med_busted:.1f}")
        print(f"median delta (BUSTED-REUSED): {delta_med:+.1f} ms")
        print(f"median ratio (BUSTED/REUSED): {ratio_med:.2f}x")
        print(f"trimmed-mean REUSED ({args.trim_frac:.2f}): {tmean_reused:.1f} ms")
        print(f"trimmed-mean BUSTED ({args.trim_frac:.2f}): {tmean_busted:.1f} ms")
        print(f"trimmed delta (BUSTED-REUSED): {delta_tmean:+.1f} ms")
        print(f"trimmed ratio (BUSTED/REUSED): {ratio_tmean:.2f}x")
    else:
        print("Not enough valid first_chunk_ms samples.")

    if reused_cached and busted_cached:
        print(f"avg cached_tokens REUSED: {statistics.mean(reused_cached):.1f}")
        print(f"avg cached_tokens BUSTED: {statistics.mean(busted_cached):.1f}")


if __name__ == "__main__":
    main()

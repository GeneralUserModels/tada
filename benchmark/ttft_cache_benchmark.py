#!/usr/bin/env python3
"""
TTFT cache benchmark: grid sweep across models, prompt sizes, and cache ratios.

Runs every combination of (model, total_tokens, cache_pct) and reports a
structured comparison table showing how prefix caching affects TTFT.

For each cell in the grid:
  1) Warm the prefix once.
  2) Run N trials, each with a REUSED_PREFIX and BUSTED_PREFIX arm in random order.
  3) Collect median/trimmed-mean first_chunk_ms and cached_tokens for both arms.

API keys are loaded from benchmark/.env (see .env.example):
  GEMINI_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import statistics
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

_BENCHMARK_DIR = Path(__file__).resolve().parent
load_dotenv(_BENCHMARK_DIR / ".env")

_ENV_VAR_FOR_PROVIDER: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _provider_of(model: str) -> str:
    lower = model.lower()
    if "claude" in lower or "anthropic" in lower:
        return "anthropic"
    if "gemini" in lower or "google" in lower:
        return "gemini"
    return "openai"


def _resolve_api_key(model: str) -> str | None:
    """Return the env-var API key for a model's provider, or None (litellm will try its own lookup)."""
    env_var = _ENV_VAR_FOR_PROVIDER.get(_provider_of(model), "OPENAI_API_KEY")
    return os.environ.get(env_var) or None


@lru_cache(maxsize=4)
def _get_tokenizer(encoding_name: str):
    import tiktoken

    return tiktoken.get_encoding(encoding_name)


def _tokenish_text(n_tokens: int, prefix: str, encoding_name: str) -> str:
    """Create text with approximately exact token length using tiktoken."""
    if n_tokens <= 0:
        return ""
    enc = _get_tokenizer(encoding_name)
    token_ids: list[int] = []
    i = 0
    while len(token_ids) < n_tokens:
        piece = f"{prefix}_{i % 1000}"
        piece_text = piece if i == 0 else f" {piece}"
        piece_ids = enc.encode(piece_text)
        if piece_ids:
            token_ids.extend(piece_ids)
        i += 1
    return enc.decode(token_ids[:n_tokens])


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


def _mode_for_model(model: str) -> str:
    """Auto-detect whether to use explicit cache_control blocks.

    Anthropic: explicit cache_control works well and is needed for reliable caching.
    Gemini: litellm translates cache_control into Google's Context Caching API, which
      adds ~2s overhead per call (separate create/lookup round-trips) and defeats our
      bust methodology. Gemini's implicit prefix caching is better for TTFT benchmarks.
    OpenAI: automatic prefix caching, no hints needed.
    """
    lower = model.lower()
    if "claude" in lower or "anthropic" in lower:
        return "cache_control"
    return "plain"


def _measure_prompt_tokens(model: str, api_key: str, text: str) -> int | None:
    """Send text as a user message and return prompt_tokens from usage."""
    from litellm import completion

    kwargs: dict[str, Any] = dict(
        model=model,
        api_key=api_key or None,
        messages=[{"role": "user", "content": text}],
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=1,
    )
    if "gpt-5" not in model.lower():
        kwargs["temperature"] = 0

    prompt_tokens = None
    for chunk in completion(**kwargs):
        usage = getattr(chunk, "usage", None)
        if usage is not None:
            pt = getattr(usage, "prompt_tokens", None)
            if pt is not None:
                prompt_tokens = pt

    return prompt_tokens


def calibrate_model(model: str, encoding: str) -> float:
    """Calibrate at a large token count to get an accurate ratio.

    Returns model_tokens / tiktoken_tokens.
    """
    api_key = _resolve_api_key(model)
    tik_count = 20000
    text = _tokenish_text(tik_count, "cal", encoding)

    pt = _measure_prompt_tokens(model, api_key, text)
    if not pt or pt <= 0:
        print(f"    WARNING: calibration failed for {model}, falling back to ratio=1.0")
        return 1.0

    return pt / tik_count


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
    dynamic = f"nonce_{nonce}\n{dynamic_suffix}\nReturn exactly: OK"
    if mode == "cache_control" and static_prefix:
        content = [
            {
                "type": "text",
                "text": static_prefix,
                "cache_control": {"type": "ephemeral"},
            },
            {"type": "text", "text": dynamic},
        ]
    else:
        content = f"{static_prefix}\n{dynamic}" if static_prefix else dynamic

    t0 = time.perf_counter()
    ttft_ms = None
    first_chunk_ms = None
    prompt_tokens = None
    cached_tokens = None

    kwargs: dict[str, Any] = dict(
        model=model,
        api_key=api_key or None,
        messages=[{"role": "user", "content": content}],
        stream=True,
        stream_options={"include_usage": True},
        max_tokens=max_tokens,
    )
    if "gpt-5" not in model.lower():
        kwargs["temperature"] = 0

    stream = completion(**kwargs)

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
                cached_tokens = getattr(usage, "cache_read_input_tokens", None)

    return {
        "ttft_ms": _safe_float(ttft_ms),
        "first_chunk_ms": _safe_float(first_chunk_ms),
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
    }


@dataclass
class ExperimentResult:
    model: str
    total_tokens: int
    cache_pct: int
    cached_tokens_target: int
    runs: int
    reused_first_chunks: list[float] = field(default_factory=list)
    busted_first_chunks: list[float] = field(default_factory=list)
    reused_cached_counts: list[float] = field(default_factory=list)
    busted_cached_counts: list[float] = field(default_factory=list)
    error: str | None = None


def trimmed_mean(vals: list[float], frac: float) -> float:
    if not vals:
        return float("nan")
    xs = sorted(vals)
    k = int(len(xs) * frac)
    core = xs[k : len(xs) - k] if len(xs) - 2 * k > 0 else xs
    return statistics.mean(core)


def run_experiment(
    *,
    model: str,
    total_tokens: int,
    cache_pct: int,
    runs: int,
    max_tokens: int,
    encoding: str,
    seed: int,
    token_ratio: float = 1.0,
) -> ExperimentResult:
    tiktoken_total = round(total_tokens / token_ratio)
    cached_tok = int(tiktoken_total * cache_pct / 100)
    dynamic_tok = tiktoken_total - cached_tok
    mode = _mode_for_model(model)
    api_key = _resolve_api_key(model)

    result = ExperimentResult(
        model=model,
        total_tokens=total_tokens,
        cache_pct=cache_pct,
        cached_tokens_target=int(total_tokens * cache_pct / 100),
        runs=runs,
    )

    try:
        static_prefix = _tokenish_text(cached_tok, "cache", encoding)
        dynamic_suffix = _tokenish_text(dynamic_tok, "tail", encoding)
    except Exception as e:
        result.error = f"encoding error: {e}"
        return result

    rng = random.Random(seed)
    max_attempts = runs * 3

    try:
        if cache_pct == 0:
            for i in range(runs):
                out = run_call(
                    model=model,
                    api_key=api_key,
                    static_prefix=static_prefix,
                    dynamic_suffix=dynamic_suffix,
                    max_tokens=max_tokens,
                    mode=mode,
                )
                if isinstance(out["first_chunk_ms"], (int, float)):
                    ms = float(out["first_chunk_ms"])
                    result.reused_first_chunks.append(ms)
                    result.busted_first_chunks.append(ms)

                pt_info = f"  prompt_toks={out['prompt_tokens']}" if out.get("prompt_tokens") else ""
                print(
                    f"  [{i + 1}/{runs}] baseline={out['first_chunk_ms']:.1f}ms{pt_info}"
                    if isinstance(out["first_chunk_ms"], (int, float))
                    else f"  [{i + 1}/{runs}] (partial data)"
                )
        else:
            good_runs: list[tuple[dict, dict]] = []
            max_cached: float | None = None
            attempt = 0

            while len(good_runs) < runs and attempt < max_attempts:
                attempt += 1

                # Warm the prefix, then measure reused vs busted
                run_call(
                    model=model,
                    api_key=api_key,
                    static_prefix=static_prefix,
                    dynamic_suffix=dynamic_suffix,
                    max_tokens=max_tokens,
                    mode=mode,
                )
                order = ["REUSED_PREFIX", "BUSTED_PREFIX"]
                rng.shuffle(order)
                trial: dict[str, dict] = {}
                for arm in order:
                    pfx = static_prefix if arm == "REUSED_PREFIX" else _bust_prefix_at_start(static_prefix)
                    out = run_call(
                        model=model,
                        api_key=api_key,
                        static_prefix=pfx,
                        dynamic_suffix=dynamic_suffix,
                        max_tokens=max_tokens,
                        mode=mode,
                    )
                    trial[arm] = out

                r, b = trial["REUSED_PREFIX"], trial["BUSTED_PREFIX"]
                r_cached = r["cached_tokens"]

                # Determine if this is a full cache hit (0 means cache miss).
                # Allow 1% tolerance for providers with slight token count variation.
                is_good = False
                if isinstance(r_cached, (int, float)) and r_cached > 0:
                    if max_cached is None or r_cached > max_cached:
                        if max_cached is not None and r_cached > max_cached:
                            tol = max_cached * 0.01
                            old_count = len(good_runs)
                            good_runs = [
                                (gr, gb) for gr, gb in good_runs
                                if isinstance(gr["cached_tokens"], (int, float))
                                and gr["cached_tokens"] >= r_cached - tol
                            ]
                            if old_count > len(good_runs):
                                print(f"  >> new max {r_cached} > {max_cached}, discarded {old_count - len(good_runs)} old runs")
                        max_cached = r_cached
                        is_good = True
                    elif max_cached is not None and r_cached >= max_cached * 0.99:
                        is_good = True

                if is_good:
                    good_runs.append((r, b))
                    status = f"ok {len(good_runs)}/{runs}"
                else:
                    status = f"skip (cached_toks={r_cached}, want {max_cached})"

                print(
                    f"  [{attempt}] reused={r['first_chunk_ms']:.1f}ms "
                    f"busted={b['first_chunk_ms']:.1f}ms "
                    f"cached_toks={r['cached_tokens']}/{b['cached_tokens']}  [{status}]"
                    if isinstance(r["first_chunk_ms"], (int, float))
                    and isinstance(b["first_chunk_ms"], (int, float))
                    else f"  [{attempt}] (partial data)  [{status}]"
                )

            if not good_runs:
                print(f"  >> no full cache hits in {attempt} attempts; falling back to all runs")

            for r, b in good_runs:
                if isinstance(r["first_chunk_ms"], (int, float)):
                    result.reused_first_chunks.append(float(r["first_chunk_ms"]))
                if isinstance(b["first_chunk_ms"], (int, float)):
                    result.busted_first_chunks.append(float(b["first_chunk_ms"]))
                if isinstance(r["cached_tokens"], (int, float)):
                    result.reused_cached_counts.append(float(r["cached_tokens"]))
                if isinstance(b["cached_tokens"], (int, float)):
                    result.busted_cached_counts.append(float(b["cached_tokens"]))

            print(f"  >> {len(good_runs)}/{attempt} attempts kept (expected cached_toks={max_cached})")

    except Exception as e:
        result.error = str(e)

    return result


def _fmt(v: float) -> str:
    if v != v:  # nan
        return "n/a"
    return f"{v:.1f}"


def print_results_table(results: list[ExperimentResult], trim_frac: float) -> None:
    header = (
        f"{'model':<40} {'tokens':>7} {'cache%':>6} "
        f"{'med_reuse':>10} {'med_bust':>10} {'delta':>8} {'ratio':>7} "
        f"{'avg_cached_r':>12} {'avg_cached_b':>12} {'err':>5}"
    )
    sep = "-" * len(header)

    print(f"\n{'=' * len(header)}")
    print("SWEEP RESULTS")
    print(f"{'=' * len(header)}")
    print(header)
    print(sep)

    for r in results:
        if r.error and not r.reused_first_chunks:
            print(
                f"{r.model:<40} {r.total_tokens:>7} {r.cache_pct:>5}% "
                f"{'ERROR':>10} {'':<10} {'':<8} {'':<7} "
                f"{'':<12} {'':<12} {r.error[:40]}"
            )
            continue

        med_r = statistics.median(r.reused_first_chunks) if r.reused_first_chunks else float("nan")
        med_b = statistics.median(r.busted_first_chunks) if r.busted_first_chunks else float("nan")
        delta = med_b - med_r
        ratio = med_b / med_r if med_r > 0 else float("nan")
        avg_cr = statistics.mean(r.reused_cached_counts) if r.reused_cached_counts else float("nan")
        avg_cb = statistics.mean(r.busted_cached_counts) if r.busted_cached_counts else float("nan")
        err_flag = "*" if r.error else ""

        print(
            f"{r.model:<40} {r.total_tokens:>7} {r.cache_pct:>5}% "
            f"{_fmt(med_r):>10} {_fmt(med_b):>10} {f'{delta:+.1f}':>8} {f'{ratio:.2f}x':>7} "
            f"{_fmt(avg_cr):>12} {_fmt(avg_cb):>12} {err_flag:>5}"
        )

    print(sep)

    # Per-model summary
    models_seen = sorted(set(r.model for r in results))
    if len(models_seen) > 1:
        print(f"\n{'=' * 60}")
        print("PER-MODEL AGGREGATE (trimmed-mean across all configs)")
        print(f"{'=' * 60}")
        for m in models_seen:
            subset = [r for r in results if r.model == m and r.reused_first_chunks]
            all_reused = [v for r in subset for v in r.reused_first_chunks]
            all_busted = [v for r in subset for v in r.busted_first_chunks]
            if all_reused and all_busted:
                tm_r = trimmed_mean(all_reused, trim_frac)
                tm_b = trimmed_mean(all_busted, trim_frac)
                print(
                    f"  {m:<38} reused={tm_r:.1f}ms  busted={tm_b:.1f}ms  "
                    f"delta={tm_b - tm_r:+.1f}ms  ratio={tm_b / tm_r:.2f}x"
                )


def _result_to_row(r: ExperimentResult, trim_frac: float) -> dict:
    med_r = statistics.median(r.reused_first_chunks) if r.reused_first_chunks else None
    med_b = statistics.median(r.busted_first_chunks) if r.busted_first_chunks else None
    return {
        "model": r.model,
        "total_tokens": r.total_tokens,
        "cache_pct": r.cache_pct,
        "cached_tokens_target": r.cached_tokens_target,
        "runs": r.runs,
        "median_reused_ms": med_r,
        "median_busted_ms": med_b,
        "delta_ms": (med_b - med_r) if med_r is not None and med_b is not None else None,
        "ratio": (med_b / med_r) if med_r and med_r > 0 else None,
        "trimmed_mean_reused_ms": trimmed_mean(r.reused_first_chunks, trim_frac) if r.reused_first_chunks else None,
        "trimmed_mean_busted_ms": trimmed_mean(r.busted_first_chunks, trim_frac) if r.busted_first_chunks else None,
        "avg_cached_tokens_reused": statistics.mean(r.reused_cached_counts) if r.reused_cached_counts else None,
        "avg_cached_tokens_busted": statistics.mean(r.busted_cached_counts) if r.busted_cached_counts else None,
        "raw_reused_ms": r.reused_first_chunks,
        "raw_busted_ms": r.busted_first_chunks,
        "error": r.error,
    }


def _experiment_key(model: str, total_tokens: int, cache_pct: int) -> str:
    return f"{model}|{total_tokens}|{cache_pct}"


def load_previous_results(path: Path) -> tuple[list[dict], set[str]]:
    """Load existing results JSON and return (rows, set of completed experiment keys)."""
    if not path.exists():
        return [], set()
    try:
        rows = json.loads(path.read_text())
    except Exception:
        return [], set()
    done = {_experiment_key(r["model"], r["total_tokens"], r["cache_pct"]) for r in rows}
    return rows, done


def _row_to_result(row: dict) -> ExperimentResult:
    return ExperimentResult(
        model=row["model"],
        total_tokens=row["total_tokens"],
        cache_pct=row["cache_pct"],
        cached_tokens_target=row.get("cached_tokens_target", 0),
        runs=row.get("runs", 0),
        reused_first_chunks=row.get("raw_reused_ms", []),
        busted_first_chunks=row.get("raw_busted_ms", []),
        reused_cached_counts=[],
        busted_cached_counts=[],
        error=row.get("error"),
    )


def save_results(rows: list[dict], path: Path) -> None:
    path.write_text(json.dumps(rows, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep TTFT cache benchmark across models, prompt sizes, and cache ratios."
    )
    parser.add_argument(
        "--models",
        nargs="+",
        default=[
            "gemini/gemini-3.1-flash-lite-preview",
            "gemini/gemini-3.1-pro-preview",
            "openai/gpt-5-mini",
            "openai/gpt-5",
            "anthropic/claude-sonnet-4-6",
            "anthropic/claude-opus-4-6",
        ],
        help="Models to test (litellm format).",
    )
    parser.add_argument(
        "--total-tokens",
        nargs="+",
        type=int,
        default=[20000, 40000, 80000, 160000],
        help="Total prompt token counts to test.",
    )
    parser.add_argument(
        "--cache-pcts",
        nargs="+",
        type=int,
        default=[0, 25, 50, 75, 100],
        help="Percentage of total tokens to cache (0-100).",
    )
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--max-tokens", type=int, default=16)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--trim-frac", type=float, default=0.2)
    parser.add_argument(
        "--encoding",
        default="o200k_base",
        help="tiktoken encoding for constructing token-length-controlled prompts.",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        default="results.json",
        help="Path to write JSON results (also used for resume).",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore existing results and start fresh.",
    )
    args = parser.parse_args()

    try:
        import litellm  # noqa: F401
    except ModuleNotFoundError as exc:
        raise SystemExit("Missing dependency: litellm.") from exc
    try:
        _get_tokenizer(args.encoding)
    except Exception as exc:
        raise SystemExit(f"Failed to load encoding '{args.encoding}': {exc}") from exc

    print("API keys:")
    for m in args.models:
        key = _resolve_api_key(m)
        env_var = _ENV_VAR_FOR_PROVIDER.get(_provider_of(m), "OPENAI_API_KEY")
        display = f"...{key[-4:]}" if key else "MISSING"
        print(f"  {m}: {env_var}={display}")
    print()

    print("Calibrating tokenizer ratios (1 API call per model at 20k tiktoken):")
    token_ratios: dict[str, float] = {}
    for m in args.models:
        ratio = calibrate_model(m, encoding=args.encoding)
        token_ratios[m] = ratio
        print(f"  {m}: ratio={ratio:.4f}x  (40k target → {round(40000 / ratio)} tiktoken)")
    print()

    for pct in args.cache_pcts:
        if not (0 <= pct <= 100):
            raise SystemExit(f"--cache-pcts values must be 0-100, got {pct}")

    json_path = Path(args.json_out)
    if args.no_resume:
        saved_rows: list[dict] = []
        done_keys: set[str] = set()
    else:
        saved_rows, done_keys = load_previous_results(json_path)

    grid = list(itertools.product(args.models, args.total_tokens, args.cache_pcts))
    total_experiments = len(grid)
    skipped = sum(1 for m, t, p in grid if _experiment_key(m, t, p) in done_keys)

    print(f"\n{'=' * 60}")
    print(f"TTFT CACHE SWEEP: {total_experiments} experiments ({skipped} cached, {total_experiments - skipped} remaining)")
    print(f"  models:      {args.models}")
    print(f"  total_tokens: {args.total_tokens}")
    print(f"  cache_pcts:  {args.cache_pcts}")
    print(f"  runs/exp:    {args.runs}")
    print(f"{'=' * 60}\n")

    results: list[ExperimentResult] = [_row_to_result(r) for r in saved_rows]

    for idx, (model, tok, pct) in enumerate(grid, 1):
        key = _experiment_key(model, tok, pct)
        if key in done_keys:
            print(f"[{idx}/{total_experiments}] CACHED  model={model}  tokens={tok}  cache={pct}%")
            continue

        print(f"[{idx}/{total_experiments}] model={model}  tokens={tok}  cache={pct}%")
        result = run_experiment(
            model=model,
            total_tokens=tok,
            cache_pct=pct,
            runs=args.runs,
            max_tokens=args.max_tokens,
            encoding=args.encoding,
            seed=args.seed,
            token_ratio=token_ratios.get(model, 1.0),
        )
        results.append(result)
        if result.error:
            print(f"  !! error: {result.error}")

        saved_rows.append(_result_to_row(result, args.trim_frac))
        save_results(saved_rows, json_path)
        print()

    print_results_table(results, args.trim_frac)
    print(f"\nResults saved to {json_path}")


if __name__ == "__main__":
    main()

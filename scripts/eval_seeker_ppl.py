"""
Evaluate seeker conversation impact using perplexity (log-probability).

Mirrors the actual user model pipeline:
  1. Think — model generates rationale (all samples fired simultaneously)
  2. Retrieve — BM25 retrieval based on rationale (sequential, CPU)
  3. Revise — model revises reasoning (all samples fired simultaneously)
  4. Logprobs — compute log-probability of ground truth (all fired simultaneously)

Runs this pipeline twice per sample (vanilla vs seeker-augmented) and
compares perplexity. Lower perplexity = better prediction.

Usage:
    uv run python scripts/build_seeker_eval.py
    uv run python scripts/eval_seeker_ppl.py [--input logs/seeker_eval.parquet]
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
import tinker
from tqdm import tqdm
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.renderers.qwen3 import Qwen3VLInstructRenderer
from tinker_cookbook.image_processing_utils import get_image_processor

from retrievers import InMemoryBM25Temporal, jaccard_ngrams, mmr_select
from user_models.powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION,
    build_think_user_message,
    build_revise_user_message,
    build_actions_user_message,
)


def build_initial_messages(row: pd.Series, seeker: bool) -> list[dict]:
    """Build the initial user message with past actions (and optionally seeker context)."""
    text = TASK_DESCRIPTION + "\n\n"
    if seeker and row["seeker_text"]:
        text += (
            "Here are conversations with the user that reveal their goals, "
            "preferences, and context:\n\n"
            f"{row['seeker_text']}\n\n"
        )
    text += row["past_actions"]
    # Merge think instruction into the user message
    think_msg = build_think_user_message()
    text += "\n\n" + think_msg["content"]
    return [{"role": "user", "content": [{"type": "text", "text": text}]}]


def do_retrieval(retriever, think_text, row):
    """Run BM25 retrieval using think output + past actions + dense caption."""
    query = think_text
    if row["past_actions"]:
        query += "\n\n" + row["past_actions"]
    if row["dense_caption"]:
        query += "\n\n" + row["dense_caption"]

    if retriever is None:
        return ""
    hits = retriever.query(
        query, k=10, cutoff_ts=int(row["boundary_ts"]),
        namespaces=["train"], time_decay_lambda=0.5,
    )
    if hits:
        items = [(h["text"], h["score"], h) for h in hits]
        selected = mmr_select(items, top_m=5, alpha=0.5)
        hits = [it[2] for it in selected]
    return "\n\n".join(h["text"] for h in hits)


def extract_gt_logprobs(logprobs, prompt_len, num_gt_tokens):
    """Extract mean logprob and perplexity for ground truth tokens."""
    gt_lps = []
    for i in range(prompt_len, prompt_len + num_gt_tokens):
        if i < len(logprobs) and logprobs[i] is not None:
            gt_lps.append(logprobs[i])
    if not gt_lps:
        return {"mean_logprob": float("-inf"), "perplexity": float("inf"),
                "num_gt_tokens": 0, "num_prompt_tokens": prompt_len}
    mean_lp = sum(gt_lps) / len(gt_lps)
    return {
        "mean_logprob": mean_lp,
        "perplexity": math.exp(-mean_lp),
        "num_gt_tokens": len(gt_lps),
        "num_prompt_tokens": prompt_len,
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate seeker impact via perplexity")
    parser.add_argument("--input", default="./logs/seeker_eval.parquet")
    parser.add_argument("--model", default=None)
    parser.add_argument("--num-samples", type=int, default=None, help="Max samples to evaluate (default: all)")
    parser.add_argument("--retriever-checkpoint", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config = json.loads(Path("powernap-config.json").read_text())
    model_name = args.model or config.get("model", "Qwen/Qwen3-VL-30B-A3B-Instruct")

    input_path = Path(args.input)
    log_dir = input_path.parent
    output_path = Path(args.output) if args.output else log_dir / "seeker_eval_ppl_results.json"

    df = pd.read_parquet(input_path)
    if args.num_samples is not None:
        df = df.head(args.num_samples)
    n = len(df)
    print(f"Loaded {n} samples from {input_path}")
    print(f"Model: {model_name}")

    # Set up tinker
    print("Creating tinker sampling client...")
    service_client = tinker.ServiceClient()
    sampling_client = service_client.create_sampling_client(base_model=model_name)
    tokenizer = get_tokenizer(model_name)
    image_processor = get_image_processor(model_name)
    renderer = Qwen3VLInstructRenderer(tokenizer, image_processor, strip_thinking_from_history=False)

    # Set up retriever
    retriever_ckpt = args.retriever_checkpoint
    if not retriever_ckpt:
        ckpts = sorted(log_dir.glob("retriever_step_*.json.gz"))
        retriever_ckpt = str(ckpts[-1]) if ckpts else None

    retriever = InMemoryBM25Temporal(
        dedup_threshold=0.8,
        dedup_sim_fn=lambda a, b: jaccard_ngrams(a, b, n=3),
    )
    if retriever_ckpt:
        print(f"Loading retriever from {retriever_ckpt}")
        retriever.load_checkpoint(retriever_ckpt)

    sample_params = tinker.SamplingParams(stop=["</rationale>"], max_tokens=512, temperature=1.0)
    revise_params = tinker.SamplingParams(stop=["</revise>"], max_tokens=512, temperature=1.0)

    # Build all jobs: each sample gets a vanilla and seeker run
    # jobs[i] = vanilla for sample i, jobs[n+i] = seeker for sample i
    rows = [row for _, row in df.iterrows()]

    # =========================================================================
    # Stage 1: Think — fire all simultaneously
    # =========================================================================
    print(f"\nStage 1: Think ({n * 2} calls)...")
    think_messages = []  # len = 2*n
    for row in rows:
        think_messages.append(build_initial_messages(row, seeker=False))
    for row in rows:
        think_messages.append(build_initial_messages(row, seeker=True))

    think_inputs = [renderer.build_generation_prompt(m) for m in think_messages]
    think_futures = [
        sampling_client.sample(prompt=inp, num_samples=1, sampling_params=sample_params)
        for inp in think_inputs
    ]
    think_texts = []
    for fut in tqdm(think_futures, desc="Think", unit="call"):
        result = fut.result()
        think_texts.append(tokenizer.decode(result.sequences[0].tokens, skip_special_tokens=True))

    # =========================================================================
    # Stage 2: Retrieve — sequential CPU work, build revise messages
    # =========================================================================
    print(f"\nStage 2: Retrieve + build revise messages...")
    revise_messages = []  # len = 2*n
    for idx in tqdm(range(2 * n), desc="Retrieve", unit="sample"):
        row = rows[idx % n]
        think_text = think_texts[idx]
        msgs = think_messages[idx]

        # Retrieval
        retrieved_text = do_retrieval(retriever, think_text, row)

        # Build revise conversation
        msgs_with_think = msgs + [{"role": "assistant", "content": think_text}]
        msgs_with_revise_prompt = msgs_with_think + [build_revise_user_message(retrieved_text)]
        revise_messages.append(msgs_with_revise_prompt)

    # =========================================================================
    # Stage 3: Revise — fire all simultaneously
    # =========================================================================
    print(f"\nStage 3: Revise ({n * 2} calls)...")
    revise_inputs = [renderer.build_generation_prompt(m) for m in revise_messages]
    revise_futures = [
        sampling_client.sample(prompt=inp, num_samples=1, sampling_params=revise_params)
        for inp in revise_inputs
    ]
    revise_texts = []
    for fut in tqdm(revise_futures, desc="Revise", unit="call"):
        result = fut.result()
        revise_texts.append(tokenizer.decode(result.sequences[0].tokens, skip_special_tokens=True))

    # =========================================================================
    # Stage 4: Logprobs — fire all simultaneously
    # =========================================================================
    print(f"\nStage 4: Logprobs ({n * 2} calls)...")
    logprob_prompt_lens = []
    logprob_gt_lens = []
    logprob_futures = []

    for idx in range(2 * n):
        row = rows[idx % n]
        revise_text = revise_texts[idx]

        # Build full conversation up to actions prompt
        full_msgs = revise_messages[idx] + [
            {"role": "assistant", "content": revise_text},
            build_actions_user_message(row["future_len"]),
        ]
        prompt_input = renderer.build_generation_prompt(full_msgs)
        prompt_len = prompt_input.length

        # Create new ModelInput with ground truth tokens appended (same pattern as trainer)
        gt_tokens = tokenizer.encode(row["ground_truth"], add_special_tokens=False)
        full_input = tinker.ModelInput(chunks=list(prompt_input.chunks) + [
            tinker.EncodedTextChunk(tokens=gt_tokens)
        ])

        logprob_prompt_lens.append(prompt_len)
        logprob_gt_lens.append(len(gt_tokens))
        logprob_futures.append(sampling_client.compute_logprobs(full_input))

    logprob_results = []
    for fut, p_len, gt_len in tqdm(
        zip(logprob_futures, logprob_prompt_lens, logprob_gt_lens),
        total=2 * n, desc="Logprobs", unit="call",
    ):
        logprobs = fut.result()
        logprob_results.append(extract_gt_logprobs(logprobs, p_len, gt_len))

    # =========================================================================
    # Assemble results
    # =========================================================================
    results = []
    for i in range(n):
        vanilla = logprob_results[i]
        seeker = logprob_results[n + i]
        delta_lp = seeker["mean_logprob"] - vanilla["mean_logprob"]

        results.append({
            "sample_idx": int(rows[i]["sample_idx"]),
            "boundary_ts": float(rows[i]["boundary_ts"]),
            "boundary_time": rows[i]["boundary_time"],
            "vanilla_mean_logprob": vanilla["mean_logprob"],
            "vanilla_perplexity": vanilla["perplexity"],
            "vanilla_prompt_tokens": vanilla["num_prompt_tokens"],
            "seeker_mean_logprob": seeker["mean_logprob"],
            "seeker_perplexity": seeker["perplexity"],
            "seeker_prompt_tokens": seeker["num_prompt_tokens"],
            "gt_tokens": vanilla["num_gt_tokens"],
            "delta_logprob": delta_lp,
        })

    # Aggregate
    def mean(vals):
        return sum(vals) / len(vals) if vals else 0.0

    v_lp = mean([r["vanilla_mean_logprob"] for r in results])
    s_lp = mean([r["seeker_mean_logprob"] for r in results])
    v_ppl = mean([r["vanilla_perplexity"] for r in results])
    s_ppl = mean([r["seeker_perplexity"] for r in results])

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nTotal samples: {len(results)}")

    print(f"\n{'':>25} {'Vanilla':>12} {'Seeker':>12} {'Delta':>12}")
    print(f"{'Mean logprob':>25} {v_lp:>12.4f} {s_lp:>12.4f} {s_lp - v_lp:>+12.4f}")
    print(f"{'Perplexity':>25} {v_ppl:>12.2f} {s_ppl:>12.2f} {v_ppl - s_ppl:>+12.2f}")

    wins = sum(1 for r in results if r["delta_logprob"] > 0)
    losses = sum(1 for r in results if r["delta_logprob"] < 0)
    ties = sum(1 for r in results if r["delta_logprob"] == 0)
    print(f"\n  Seeker wins: {wins}  |  Ties: {ties}  |  Vanilla wins: {losses}")

    # Per-sample detail
    print(f"\n--- Per-sample ---")
    for r in results:
        print(
            f"  {r['boundary_time']} | "
            f"v_ppl={r['vanilla_perplexity']:>8.2f}  s_ppl={r['seeker_perplexity']:>8.2f}  "
            f"delta_lp={r['delta_logprob']:+.4f}"
        )

    # Save
    output_data = {
        "config": {"model": model_name, "input": str(input_path)},
        "summary": {
            "total_samples": len(results),
            "vanilla_mean_logprob": v_lp,
            "seeker_mean_logprob": s_lp,
            "delta_logprob": s_lp - v_lp,
            "vanilla_perplexity": v_ppl,
            "seeker_perplexity": s_ppl,
            "seeker_wins": wins,
            "vanilla_wins": losses,
            "ties": ties,
        },
        "samples": results,
    }
    output_path.write_text(json.dumps(output_data, indent=2))
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()

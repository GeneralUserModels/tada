"""
Evaluate whether seeker conversations improve next-action prediction accuracy.

Reads a parquet dataset (built by build_seeker_eval.py) and for each sample runs:
  1. Vanilla — standard prompted predictor (no seeker context)
  2. Seeker-augmented — same predictor with seeker conversation text injected

Both are scored by the LLM accuracy judge. Uses litellm.batch_completion to
parallelize all LLM calls for speed.

Usage:
    uv run python scripts/build_seeker_eval.py  # create the dataset first
    uv run python scripts/eval_seeker.py [--input logs/seeker_eval.parquet]
"""

import argparse
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

import pandas as pd
from tqdm import tqdm

from litellm import batch_completion
from user_models.powernap.longnap.trainer_utils import TASK_DESCRIPTION

logging.basicConfig(level=logging.WARNING)


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def build_prediction_messages(row: pd.Series, seeker: bool) -> list[dict]:
    """Build the messages for a single prediction call."""
    text = row["task_description"] + "\n\n"
    if seeker and row["seeker_text"]:
        text += (
            "Here are conversations with the user that reveal their goals, "
            "preferences, and context:\n\n"
            f"{row['seeker_text']}\n\n"
        )
    text += row["past_actions"]
    text += (
        f"\n\nPredict the next {row['future_len']} actions the user will take. "
        f"Output ONLY <action>...</action> tags inside a larger <actions>...</actions> block, "
        f"with each action wrapped in its own <action> tag."
    )
    return [{"role": "user", "content": text}]


def build_scoring_prompt(predicted_actions: str, ground_truth: str, prompt_template: str) -> str | None:
    """Build a scoring prompt, or None if prediction is invalid."""
    if not predicted_actions or not re.search(r"<action>", predicted_actions):
        return None
    if "<actions>" not in predicted_actions or "</actions>" not in predicted_actions:
        return None
    expected = len(re.findall(r"<action>.*?</action>", ground_truth, re.DOTALL))
    actual = len(re.findall(r"<action>.*?</action>", predicted_actions, re.DOTALL))
    if actual != expected:
        return None
    return prompt_template.format(
        ground_truth=ground_truth,
        candidates=f"- **Candidate 1**:\n{predicted_actions}\n",
    )


def parse_score(response_text: str) -> float:
    """Parse the accuracy score from a judge response."""
    text = (response_text or "").strip()
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    if json_match:
        text = json_match.group(1).strip()
    parsed = json.loads(text)
    return parsed["candidates"][0]["score"]


def run_batch(model: str, messages_list: list[list[dict]], api_key: str,
              max_tokens: int = 8192, desc: str = "Batch") -> list[str]:
    """Run a batch of LLM calls and return the response texts."""
    results = []
    batch_size = 20
    for i in tqdm(range(0, len(messages_list), batch_size), desc=desc, unit="batch"):
        batch = messages_list[i:i + batch_size]
        responses = batch_completion(
            model=model,
            messages=batch,
            max_tokens=max_tokens,
            temperature=1.0,
            api_key=api_key or None,
        )
        for resp in responses:
            if isinstance(resp, Exception):
                results.append("")
            else:
                results.append(resp.choices[0].message.content or "")
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Evaluate seeker conversation impact on prediction")
    parser.add_argument("--input", default="./logs/seeker_eval.parquet")
    parser.add_argument("--model", default=None)
    parser.add_argument("--reward-llm", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    config = json.loads(Path("powernap-config.json").read_text())
    api_key = config.get("default_llm_api_key", "")
    reward_llm = args.reward_llm or "gemini/gemini-3-flash-preview"
    reward_api_key = config.get("reward_llm_api_key", "") or api_key
    model = args.model or config.get("prompted_model", "gemini/gemini-3-flash-preview")

    input_path = Path(args.input)
    output_path = Path(args.output) if args.output else input_path.parent / "seeker_eval_results.json"

    df = pd.read_parquet(input_path)
    print(f"Loaded {len(df)} samples from {input_path}")
    print(f"Config: model={model}, reward_llm={reward_llm}")

    n_pre = len(df[df["num_seeker_convos"] == 0])
    n_post = len(df[df["num_seeker_convos"] > 0])
    print(f"  Pre-seeker: {n_pre}, Post-seeker: {n_post}")

    # Load accuracy prompt template
    verifiers_dir = Path(__file__).resolve().parent.parent / "src" / "user_models" / "powernap" / "longnap" / "verifiers"
    accuracy_template = (verifiers_dir / "accuracy.txt").read_text()

    # --- Stage 1: Build all prediction prompts ---
    print(f"\nBuilding prediction prompts...")
    vanilla_msgs = []
    seeker_msgs = []
    seeker_indices = []  # which rows have seeker convos

    for _, row in df.iterrows():
        vanilla_msgs.append(build_prediction_messages(row, seeker=False))
        if row["num_seeker_convos"] > 0:
            seeker_msgs.append(build_prediction_messages(row, seeker=True))
            seeker_indices.append(int(row["sample_idx"]))

    print(f"  Vanilla: {len(vanilla_msgs)} calls, Seeker: {len(seeker_msgs)} calls")

    # --- Stage 2: Batch predict ---
    print(f"\nRunning predictions...")
    vanilla_outputs = run_batch(model, vanilla_msgs, api_key, desc="Vanilla predictions")
    seeker_outputs_raw = run_batch(model, seeker_msgs, api_key, desc="Seeker predictions") if seeker_msgs else []

    # Map seeker outputs back by sample_idx
    seeker_output_map = dict(zip(seeker_indices, seeker_outputs_raw))

    # --- Stage 3: Build scoring prompts ---
    print(f"\nBuilding scoring prompts...")
    score_jobs = []  # (result_idx, condition, prompt)
    for i, row in df.iterrows():
        idx = int(row["sample_idx"])
        gt = row["ground_truth"]

        v_prompt = build_scoring_prompt(vanilla_outputs[idx], gt, accuracy_template)
        if v_prompt:
            score_jobs.append((idx, "vanilla", v_prompt))

        s_output = seeker_output_map.get(idx, vanilla_outputs[idx])
        s_prompt = build_scoring_prompt(s_output, gt, accuracy_template)
        if s_prompt:
            score_jobs.append((idx, "seeker", s_prompt))

    print(f"  {len(score_jobs)} valid predictions to score (out of {len(df) * 2} total)")

    # --- Stage 4: Batch score ---
    print(f"\nRunning scoring...")
    score_msgs = [[{"role": "user", "content": p}] for _, _, p in score_jobs]
    score_responses = run_batch(reward_llm, score_msgs, reward_api_key, max_tokens=1024, desc="Scoring")

    # Parse scores
    score_map: dict[tuple[int, str], float] = {}
    for (idx, condition, _), resp in zip(score_jobs, score_responses):
        try:
            score_map[(idx, condition)] = parse_score(resp)
        except (json.JSONDecodeError, KeyError, IndexError):
            score_map[(idx, condition)] = 0.0

    # --- Stage 5: Assemble results ---
    results = []
    for _, row in df.iterrows():
        idx = int(row["sample_idx"])
        v_acc = score_map.get((idx, "vanilla"), 0.0)
        s_acc = score_map.get((idx, "seeker"), 0.0)
        delta = s_acc - v_acc
        results.append({
            "sample_idx": idx,
            "boundary_ts": float(row["boundary_ts"]),
            "boundary_time": row["boundary_time"],
            "num_applicable_convos": int(row["num_seeker_convos"]),
            "vanilla_actions": vanilla_outputs[idx],
            "seeker_actions": seeker_output_map.get(idx, vanilla_outputs[idx]),
            "ground_truth": row["ground_truth"],
            "vanilla_accuracy": v_acc,
            "seeker_accuracy": s_acc,
            "delta_accuracy": delta,
        })

    # --- Aggregate ---
    pre = [r for r in results if r["num_applicable_convos"] == 0]
    post = [r for r in results if r["num_applicable_convos"] > 0]

    def mean(vals):
        return sum(vals) / len(vals) if vals else 0.0

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"\nTotal samples: {len(results)}")
    print(f"Pre-seeker samples (no convos available): {len(pre)}")
    print(f"Post-seeker samples (convos available):   {len(post)}")

    if post:
        print(f"\n--- Post-seeker samples ---")
        print(f"{'':>20} {'Vanilla':>10} {'Seeker':>10} {'Delta':>10}")
        v_acc = mean([r["vanilla_accuracy"] for r in post])
        s_acc = mean([r["seeker_accuracy"] for r in post])
        print(f"{'Accuracy':>20} {v_acc:>10.3f} {s_acc:>10.3f} {s_acc - v_acc:>+10.3f}")

    if pre:
        print(f"\n--- Pre-seeker baseline ---")
        print(f"{'Accuracy':>20} {mean([r['vanilla_accuracy'] for r in pre]):>10.3f}")

    # Per-sample detail
    print(f"\n--- Per-sample ---")
    for r in results:
        marker = "*" if r["num_applicable_convos"] > 0 else " "
        print(f"  {marker} {r['boundary_time']} | v={r['vanilla_accuracy']:.3f} s={r['seeker_accuracy']:.3f} d={r['delta_accuracy']:+.3f}")

    # Save
    output_data = {
        "config": {"model": model, "reward_llm": reward_llm, "input": str(input_path)},
        "summary": {
            "total_samples": len(results),
            "pre_seeker_count": len(pre),
            "post_seeker_count": len(post),
            "pre_seeker_accuracy": mean([r["vanilla_accuracy"] for r in pre]) if pre else None,
            "post_seeker_vanilla_accuracy": mean([r["vanilla_accuracy"] for r in post]) if post else None,
            "post_seeker_seeker_accuracy": mean([r["seeker_accuracy"] for r in post]) if post else None,
            "post_seeker_delta_accuracy": mean([r["delta_accuracy"] for r in post]) if post else None,
        },
        "samples": results,
    }
    output_path.write_text(json.dumps(output_data, indent=2))
    print(f"\nFull results saved to {output_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

import argparse
import signal
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue, Empty

from transformers import AutoTokenizer

from powernap.napsack import OnlineRecorder, Labeler
from powernap.longnap.trainer import LongNAP
from powernap.longnap.trainer_utils import TASK_DESCRIPTION, build_actions_block
from powernap.inference import Predictor, ActionOverlay

try:
    import wandb
except ImportError:
    wandb = None


def make_sample(buffer, past_len, future_len, processor):
    window = buffer[-(past_len + future_len):]
    past = window[:past_len]
    future = window[past_len:]

    past_actions_block = build_actions_block(past)
    future_actions = build_actions_block(future)

    messages = [{
        "role": "user",
        "content": [{"type": "text", "text": TASK_DESCRIPTION + "\n\n" + past_actions_block}],
    }]

    prompt = processor.apply_chat_template(
        messages, add_generation_prompt=False, tokenize=False,
    )

    start_ts = datetime.strptime(past[0]["start_time"], "%Y-%m-%d_%H-%M-%S-%f").timestamp()
    end_ts = datetime.strptime(future[-1]["start_time"], "%Y-%m-%d_%H-%M-%S-%f").timestamp()

    return {
        "prompt": prompt,
        "solution": future_actions,
        "ts": start_ts,
        "end_ts": end_ts,
        "future_len": future_len,
        "past_len": past_len,
        "actions": future_actions,
        "past_actions": past_actions_block,
    }


def label_loop(recorder, labeler, trainer, label_queue, inference_buffer):
    label_count = 0

    for agg in recorder.iter_aggregations():
        t0 = time.time()
        labeled = labeler.label(agg)
        latency = time.time() - t0
        label_count += 1

        ts = datetime.strptime(labeled["start_time"], "%Y-%m-%d_%H-%M-%S-%f")
        trainer.retriever.add(
            labeled["text"],
            event_ts=int(ts.timestamp()),
            namespace="train",
        )

        label_queue.put(labeled)
        inference_buffer.append(labeled)

        if wandb and wandb.run is not None:
            log = {
                "pipeline/labels_total": label_count,
                "pipeline/label_latency_s": latency,
                "pipeline/label_text": wandb.Html(f"<pre>{labeled['text']}</pre>"),
            }

            # log screenshot + caption every 10 labels
            if label_count % 10 == 1 and labeled.get("img") and Path(labeled["img"]).exists():
                log["pipeline/label_image"] = wandb.Image(
                    labeled["img"], caption=labeled["text"][:200],
                )

            wandb.log(log)


def batch_iter(recorder, label_queue, past_len, future_len, batch_size, processor):
    min_required = past_len + future_len
    buffer = []
    batch = []
    batches_yielded = 0

    while recorder.running or not label_queue.empty():
        try:
            record = label_queue.get(timeout=1.0)
        except Empty:
            continue

        buffer.append(record)

        if len(buffer) >= min_required:
            sample = make_sample(buffer, past_len, future_len, processor)
            batch.append(sample)

            if len(batch) >= batch_size:
                batches_yielded += 1

                if wandb and wandb.run is not None:
                    wandb.log({
                        "pipeline/buffer_size": len(buffer),
                        "pipeline/batches_yielded": batches_yielded,
                    })

                yield batch
                batch = []


def _build_ground_truth(records):
    return build_actions_block(records)


def inference_loop(predictor, inference_buffer, trainer, recorder,
                   past_len, future_len, processor, predict_interval,
                   reward_llm, overlay):
    last_path = None
    prediction_count = 0
    eval_count = 0
    pending_evals = []  # (result, buffer_pos, future_len)

    while recorder.running:
        # pick up new checkpoint
        path = getattr(trainer, "latest_sampler_path", None)
        if path and path != last_path:
            predictor.model_path = path
            last_path = path
            print(f"[inference] using checkpoint: {path}")

        # make a prediction
        if predictor.model_path and len(inference_buffer) >= past_len:
            buffer_pos = len(inference_buffer)
            t0 = time.time()
            result = predictor.predict_from_buffer(
                inference_buffer, past_len, future_len, processor,
            )
            latency = time.time() - t0
            prediction_count += 1

            pending_evals.append((result, buffer_pos, future_len))

            print(f"[inference] prediction #{prediction_count}:")
            print(f"  actions: {result['actions']}")

            if overlay:
                overlay.update(result["actions"])

            if wandb and wandb.run is not None:
                wandb.log({
                    "inference/predictions_total": prediction_count,
                    "inference/latency_s": latency,
                })

        # check pending evals — score predictions whose ground truth has arrived
        still_pending = []
        for result, buf_pos, fl in pending_evals:
            if len(inference_buffer) >= buf_pos + fl:
                ground_truth = _build_ground_truth(inference_buffer[buf_pos:buf_pos + fl])
                reward = predictor.score_prediction(result["actions"], ground_truth, reward_llm)
                eval_count += 1

                print(f"[inference] eval #{eval_count}: reward={reward:.2f}")

                if wandb and wandb.run is not None:
                    wandb.log({
                        "inference/reward": reward,
                        "inference/evals_total": eval_count,
                        "inference/eval": wandb.Table(
                            columns=["step", "checkpoint", "think", "revise",
                                     "actions", "ground_truth", "reward"],
                            data=[[eval_count, result["model_path"],
                                   result["think"], result["revise"],
                                   result["actions"], ground_truth, reward]],
                        ),
                    })
            else:
                still_pending.append((result, buf_pos, fl))
        pending_evals = still_pending

        time.sleep(predict_interval)


def main():
    parser = argparse.ArgumentParser(description="Online record -> label -> train -> infer pipeline")

    # recorder
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--buffer-seconds", type=int, default=12)
    parser.add_argument("--precision", type=str, choices=["accurate", "rough"], default="accurate")

    # labeler
    parser.add_argument("--label-model", type=str, default="gemini/gemini-2.0-flash")

    # trainer
    parser.add_argument("--model", type=str, default="Qwen/Qwen3-VL-30B-A3B-Instruct")
    parser.add_argument("--reward-llm", type=str, default="gemini/gemini-3-flash-preview")
    parser.add_argument("--num-generations", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--max-completion-length", type=int, default=512)

    # pipeline
    parser.add_argument("--past-len", type=int, default=8)
    parser.add_argument("--future-len", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=2)

    # inference
    parser.add_argument("--predict-every-n-seconds", type=int, default=10)
    parser.add_argument("--disable-inference", action="store_true")
    parser.add_argument("--no-overlay", action="store_true")

    # logging
    parser.add_argument("--log-every-n-steps", type=int, default=1)
    parser.add_argument("--log-dir", type=str, default="./logs")
    parser.add_argument("--log-to-wandb", action="store_true")
    parser.add_argument("--wandb-project", type=str, default="longnap-online")

    args = parser.parse_args()

    # setup precision preset
    from record.constants import constants_manager
    constants_manager.set_preset(args.precision, verbose=False)

    # tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)

    # stage 1: recorder
    recorder = OnlineRecorder(fps=args.fps, buffer_seconds=args.buffer_seconds, log_dir=args.log_dir)

    # stage 2: labeler
    labeler = Labeler(model=args.label_model, log_dir=recorder.session_dir)

    # stage 3: trainer (initializes wandb if --log-to-wandb)
    trainer = LongNAP(
        model=args.model,
        reward_llm=args.reward_llm,
        num_generations=args.num_generations,
        learning_rate=args.learning_rate,
        max_completion_length=args.max_completion_length,
        generation_batch_size=args.batch_size,
        log_every_n_steps=args.log_every_n_steps,
        log_dir=args.log_dir,
        log_to_wandb=args.log_to_wandb,
        wandb_project=args.wandb_project,
    )

    # stage 4: predictor (shares retriever with trainer)
    predictor = Predictor(
        model_path=trainer.latest_sampler_path,
        max_tokens=args.max_completion_length,
        retriever=trainer.retriever,
        log_dir=recorder.session_dir,
    )

    # overlay (must be created on main thread for AppKit)
    overlay = None
    if not args.disable_inference and not args.no_overlay:
        overlay = ActionOverlay()

    # wire it up
    label_queue = Queue()
    inference_buffer = []

    def shutdown(sig, frame):
        if overlay:
            overlay.close()
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    recorder.start()

    label_thread = threading.Thread(
        target=label_loop,
        args=(recorder, labeler, trainer, label_queue, inference_buffer),
        daemon=True,
    )
    label_thread.start()

    if not args.disable_inference:
        inference_thread = threading.Thread(
            target=inference_loop,
            args=(predictor, inference_buffer, trainer, recorder,
                  args.past_len, args.future_len, tokenizer,
                  args.predict_every_n_seconds, args.reward_llm, overlay),
            daemon=True,
        )
        inference_thread.start()

    # training runs on a background thread so main thread can run AppKit event loop
    data = batch_iter(recorder, label_queue, args.past_len, args.future_len, args.batch_size, tokenizer)

    def train_loop():
        trainer.train(data)
        if overlay:
            overlay.close()
        recorder.stop()

    train_thread = threading.Thread(target=train_loop, daemon=True)
    train_thread.start()

    if overlay:
        overlay.run()  # blocks main thread on AppKit run loop
    else:
        train_thread.join()

    recorder.stop()


if __name__ == "__main__":
    main()

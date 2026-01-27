#!/usr/bin/env python3

import argparse
import signal
import sys
import threading
from datetime import datetime
from queue import Queue, Empty

from transformers import AutoTokenizer

from powernap.napsack import OnlineRecorder, Labeler
from powernap.longnap.trainer import LongNAP


def make_sample(buffer, past_len, future_len, processor):
    window = buffer[-(past_len + future_len):]
    past = window[:past_len]
    future = window[past_len:]

    past_actions_list = [f"<action>{r['text']}</action>" for r in past]
    past_actions_block = "<actions>\n" + "\n".join("    " + a for a in past_actions_list) + "\n</actions>"

    task_description = (
        "You will analyze user behavior and predict what the user will do next. "
        "Below are the actions the user took."
    )

    messages = [{
        "role": "user",
        "content": [{"type": "text", "text": task_description + "\n\n" + past_actions_block}],
    }]

    prompt = processor.apply_chat_template(
        messages, add_generation_prompt=False, tokenize=False,
    )

    future_actions = "<actions>\n"
    for r in future:
        future_actions += "    " + f"<action>{r['text']}</action>" + "\n"
    future_actions += "</actions>"

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


def label_loop(recorder, labeler, trainer, label_queue):
    for agg in recorder.iter_aggregations():
        labeled = labeler.label(agg)

        ts = datetime.strptime(labeled["start_time"], "%Y-%m-%d_%H-%M-%S-%f")
        trainer.retriever.add(
            labeled["text"],
            event_ts=int(ts.timestamp()),
            namespace="train",
        )

        label_queue.put(labeled)


def batch_iter(recorder, label_queue, past_len, future_len, batch_size, processor):
    min_required = past_len + future_len
    buffer = []
    batch = []

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
                yield batch
                batch = []


def main():
    parser = argparse.ArgumentParser(description="Online record → label → train pipeline")

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

    # stage 3: trainer
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

    # wire it up
    label_queue = Queue()

    def shutdown(sig, frame):
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    recorder.start()

    label_thread = threading.Thread(
        target=label_loop,
        args=(recorder, labeler, trainer, label_queue),
        daemon=True,
    )
    label_thread.start()

    data = batch_iter(recorder, label_queue, args.past_len, args.future_len, args.batch_size, tokenizer)
    trainer.train(data)

    recorder.stop()


if __name__ == "__main__":
    main()

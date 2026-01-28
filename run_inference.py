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
from powernap.inference import Predictor


def label_loop(recorder, labeler, predictor, inference_buffer):
    label_count = 0

    for agg in recorder.iter_aggregations():
        labeled = labeler.label(agg)
        label_count += 1

        ts = datetime.strptime(labeled["start_time"], "%Y-%m-%d_%H-%M-%S-%f")
        predictor.add_to_retriever(
            labeled["text"],
            event_ts=int(ts.timestamp()),
        )

        inference_buffer.append(labeled)
        print(f"[label] #{label_count}: {labeled['text'][:80]}")


def main():
    parser = argparse.ArgumentParser(description="Online record -> label -> infer pipeline")

    # recorder
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--buffer-seconds", type=int, default=12)
    parser.add_argument("--precision", type=str, choices=["accurate", "rough"], default="accurate")

    # labeler
    parser.add_argument("--label-model", type=str, default="gemini/gemini-2.0-flash")

    # inference
    parser.add_argument("--model-path", type=str, required=True,
                        help="Tinker sampler checkpoint path (e.g. tinker://uuid:train:0/sampler_weights/000080)")
    parser.add_argument("--tokenizer", type=str, default="Qwen/Qwen3-VL-30B-A3B-Instruct")
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--retriever-checkpoint", type=str, default=None)

    # pipeline
    parser.add_argument("--past-len", type=int, default=8)
    parser.add_argument("--future-len", type=int, default=4)
    parser.add_argument("--predict-every-n-seconds", type=int, default=10)

    # logging
    parser.add_argument("--log-dir", type=str, default="./logs")

    args = parser.parse_args()

    # setup precision preset
    from record.constants import constants_manager
    constants_manager.set_preset(args.precision, verbose=False)

    # tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, trust_remote_code=True)

    # stage 1: recorder
    recorder = OnlineRecorder(fps=args.fps, buffer_seconds=args.buffer_seconds, log_dir=args.log_dir)

    # stage 2: labeler
    labeler = Labeler(model=args.label_model, log_dir=recorder.session_dir)

    # stage 3: predictor
    predictor = Predictor(
        model_path=args.model_path,
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        retriever_checkpoint=args.retriever_checkpoint,
        log_dir=recorder.session_dir,
    )

    # wire it up
    inference_buffer = []

    def shutdown(sig, frame):
        recorder.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    recorder.start()

    label_thread = threading.Thread(
        target=label_loop,
        args=(recorder, labeler, predictor, inference_buffer),
        daemon=True,
    )
    label_thread.start()

    # main loop: predict from buffer
    prediction_count = 0
    while recorder.running:
        if len(inference_buffer) >= args.past_len:
            result = predictor.predict_from_buffer(
                inference_buffer, args.past_len, args.future_len, tokenizer,
            )
            prediction_count += 1

            print(f"\n[inference] prediction #{prediction_count}:")
            print(f"  think:   {result['think'][:200]}")
            print(f"  revise:  {result['revise'][:200]}")
            print(f"  actions: {result['actions']}")

        time.sleep(args.predict_every_n_seconds)

    recorder.stop()


if __name__ == "__main__":
    main()

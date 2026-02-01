#!/usr/bin/env python3
"""
Simple test script to see live labeler outputs (video chunk-based).

Usage:
    python scripts/test_labeler.py
    python scripts/test_labeler.py --chunk-size 10  # smaller chunks for faster feedback
    python scripts/test_labeler.py --disable move  # exclude mouse move events
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import signal
import sys
import time

from powernap.napsack import OnlineRecorder, Labeler


def main():
    parser = argparse.ArgumentParser(description="Test the live video chunk labeler")
    parser.add_argument("--fps", type=int, default=5)
    parser.add_argument("--buffer-seconds", type=int, default=12)
    parser.add_argument("--chunk-size", type=int, default=60,
                        help="Number of screenshots per video chunk")
    parser.add_argument("--chunk-fps", type=int, default=1,
                        help="Video encoding framerate (1 = one frame per second)")
    parser.add_argument("--chunk-workers", type=int, default=4,
                        help="Number of parallel chunk processors")
    parser.add_argument("--disable", type=str, nargs="*", default=None,
                        help="Event types to disable: move, scroll, click, key")
    parser.add_argument("--log-dir", type=str, default="./logs")
    args = parser.parse_args()

    # Build disable list
    disable = list(set(args.disable or []))

    print("=" * 60)
    print("Live Video Chunk Labeler Test")
    print("=" * 60)
    print(f"Chunk size: {args.chunk_size} screenshots per video")
    print(f"Chunk FPS: {args.chunk_fps}")
    print(f"Chunk workers: {args.chunk_workers}")
    print(f"Disabled events: {disable if disable else 'none'}")
    print("=" * 60)
    print("Start interacting with your computer...")
    print(f"Labels will appear after every {args.chunk_size} aggregations.")
    print("Press Ctrl+C to stop.")
    print("=" * 60)
    print()

    recorder = OnlineRecorder(
        fps=args.fps,
        buffer_seconds=args.buffer_seconds,
        log_dir=args.log_dir,
        disable=disable,
    )

    labeler = Labeler(
        chunk_size=args.chunk_size,
        fps=args.chunk_fps,
        max_workers=args.chunk_workers,
        log_dir=recorder.session_dir,
    )

    shutdown_requested = False

    def shutdown(sig, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            print("\n\nForced exit.")
            sys.exit(1)
        print("\n\nShutting down (processing remaining chunk)...")
        shutdown_requested = True
        recorder.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    recorder.start()

    label_count = 0
    chunk_count = 0
    chunk_buffer = []
    
    try:
        for agg in recorder.iter_aggregations():
            if shutdown_requested:
                break
                
            # Skip if no screenshot
            if agg.screenshot is None and not agg.request.screenshot_path:
                continue

            chunk_buffer.append(agg)
            print(f"\r[buffer] {len(chunk_buffer)}/{args.chunk_size} aggregations", end="", flush=True)
            
            # Check if chunk is full
            if len(chunk_buffer) >= args.chunk_size:
                print()  # newline after progress
                chunk_count += 1
                print(f"\n{'='*40}")
                print(f"Processing chunk #{chunk_count}...")
                
                t0 = time.time()
                try:
                    results = labeler.label_chunk(chunk_buffer)
                    latency = time.time() - t0
                    
                    print(f"Chunk #{chunk_count} labeled in {latency:.2f}s ({len(results)} labels)")
                    print("-" * 40)
                    
                    for result in results:
                        if not result.get("text"):
                            continue
                        label_count += 1
                        
                        print(f"[{label_count:3d}] {result['start_time']}")
                        print(f"      Label: {result['text']}")
                        print(f"      Events: {len(result['raw_events'])} events")
                        
                        # Show event breakdown
                        event_types = {}
                        for e in result['raw_events']:
                            et = e.get('event_type', 'unknown')
                            event_types[et] = event_types.get(et, 0) + 1
                        if event_types:
                            breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(event_types.items()))
                            print(f"      Breakdown: {breakdown}")
                        print()
                        
                except Exception as e:
                    print(f"[ERROR] Chunk labeling failed: {e}")
                    import traceback
                    traceback.print_exc()
                
                chunk_buffer.clear()
                print(f"{'='*40}\n")
                
    except KeyboardInterrupt:
        pass
    finally:
        # Process remaining buffer
        if chunk_buffer and not shutdown_requested:
            print(f"\n\nProcessing final chunk ({len(chunk_buffer)} aggregations)...")
            try:
                results = labeler.label_chunk(chunk_buffer)
                for result in results:
                    if result.get("text"):
                        label_count += 1
                        print(f"[{label_count:3d}] {result['text']}")
            except Exception as e:
                print(f"[ERROR] Final chunk failed: {e}")
        
        recorder.stop()
        print(f"\nTotal labels: {label_count}")
        print(f"Total chunks: {chunk_count}")
        print(f"Session saved to: {recorder.session_dir}")


if __name__ == "__main__":
    main()

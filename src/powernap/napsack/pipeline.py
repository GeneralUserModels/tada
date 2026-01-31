"""Async labeling pipeline: concurrent LLM calls with ordered output."""

import asyncio
import logging
import time
from collections import deque
from pathlib import Path

try:
    import wandb
except ImportError:
    wandb = None

logger = logging.getLogger(__name__)


def label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active):
    """Label incoming screen recordings with concurrent async LLM calls."""
    asyncio.run(_async_label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active))


async def _async_label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active):
    """Async label loop: fires off up to MAX_CONCURRENT labeling requests,
    drains results in submission order to preserve chronological ordering."""
    from PIL import Image

    MAX_CONCURRENT = 4
    label_count = 0
    skip_count = 0
    loop = asyncio.get_running_loop()

    agg_iter = iter(recorder.iter_aggregations())

    async def get_next_agg():
        return await loop.run_in_executor(None, lambda: next(agg_iter, None))

    pending = deque()  # deque of (asyncio.Task, submit_time)
    fetching = True
    fetch_task = None

    while fetching or pending:
        # Start a fetch if we have room and aren't already fetching
        if fetching and fetch_task is None and len(pending) < MAX_CONCURRENT:
            fetch_task = asyncio.create_task(get_next_agg())

        # Build wait set: oldest pending label + fetch task
        wait_set = set()
        if fetch_task is not None:
            wait_set.add(fetch_task)
        if pending:
            wait_set.add(pending[0][0])

        if not wait_set:
            break

        done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

        # Handle fetch completion
        if fetch_task in done:
            agg = fetch_task.result()
            fetch_task = None
            if agg is None:
                fetching = False
            else:
                has_screenshot = (
                    agg.screenshot is not None or
                    (agg.request.screenshot_path and Path(agg.request.screenshot_path).exists())
                )
                if has_screenshot:
                    task = asyncio.create_task(labeler.alabel(agg))
                    pending.append((task, time.time()))
                else:
                    skip_count += 1

        # Drain completed tasks from the front (preserves chronological order)
        while pending and pending[0][0].done():
            task, t0 = pending.popleft()
            try:
                labeled = task.result()
            except Exception as e:
                logger.error(f"Labeling failed: {e}")
                continue

            latency = time.time() - t0
            label_count += 1
            print(f"[label] labeled action #{label_count}: {labeled['text'][:80]}... ({latency:.2f}s, in-flight={len(pending)})")

            # always add to inference buffer
            inference_buffer.append(labeled)

            # only feed training data when sleepwalk is NOT active
            if not sleepwalk_active.is_set():
                label_queue.put(labeled)

            if wandb and wandb.run is not None:
                log = {
                    "pipeline/labels_total": label_count,
                    "pipeline/label_latency_s": latency,
                    "pipeline/label_text": wandb.Html(f"<pre>{labeled['text']}</pre>"),
                }

                if label_count % 10 == 1 and labeled.get("img") is not None:
                    img = labeled["img"]
                    if isinstance(img, Image.Image) or (isinstance(img, str) and Path(img).exists()):
                        log["pipeline/label_image"] = wandb.Image(
                            img, caption=labeled["text"][:200],
                        )

                wandb.log(log)

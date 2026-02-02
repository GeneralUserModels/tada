"""Async labeling pipeline: video chunk-based labeling with parallel processing."""

import asyncio
import logging
import time
from collections import deque

try:
    import wandb
except ImportError:
    wandb = None

logger = logging.getLogger(__name__)


def label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active):
    """Label incoming screen recordings by accumulating into video chunks."""
    asyncio.run(_async_label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active))


async def _async_label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active):
    """Async label loop: accumulates aggregations into chunks, labels via video.
    
    Uses parallel chunk processing while preserving chronological output order.
    """
    label_count = 0
    chunk_count = 0
    skip_count = 0
    loop = asyncio.get_running_loop()
    
    agg_iter = iter(recorder.iter_aggregations())
    
    async def get_next_agg():
        return await loop.run_in_executor(None, lambda: next(agg_iter, None))
    
    # Chunk accumulator
    chunk_buffer = []
    
    # Pending chunk tasks: (asyncio.Task, list[agg], submit_time)
    pending_chunks = deque()
    
    fetching = True
    fetch_task = None
    
    while fetching or pending_chunks or chunk_buffer:
        # Start a fetch if we aren't already fetching
        if fetching and fetch_task is None:
            fetch_task = asyncio.create_task(get_next_agg())
        
        # Build wait set
        wait_set = set()
        if fetch_task is not None:
            wait_set.add(fetch_task)
        if pending_chunks:
            wait_set.add(pending_chunks[0][0])
        
        if not wait_set:
            # No more work - flush remaining buffer if any
            if chunk_buffer:
                print(f"[label] flushing final chunk with {len(chunk_buffer)} aggregations")
                task = asyncio.create_task(labeler.alabel_chunk(chunk_buffer.copy()))
                pending_chunks.append((task, chunk_buffer.copy(), time.time()))
                chunk_buffer.clear()
                continue
            break
        
        # Wait with timeout to allow flushing partial chunks on shutdown
        try:
            done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED, timeout=1.0)
        except asyncio.CancelledError:
            break
        
        # Handle fetch completion
        if fetch_task in done:
            agg = fetch_task.result()
            fetch_task = None
            
            if agg is None:
                fetching = False
            else:
                if agg.screenshot is not None:
                    chunk_buffer.append(agg)
                    
                    # Check if chunk is full
                    if len(chunk_buffer) >= labeler.chunk_size:
                        chunk_count += 1
                        print(f"[label] submitting chunk #{chunk_count} with {len(chunk_buffer)} aggregations")
                        task = asyncio.create_task(labeler.alabel_chunk(chunk_buffer.copy()))
                        pending_chunks.append((task, chunk_buffer.copy(), time.time()))
                        chunk_buffer.clear()
                else:
                    skip_count += 1
        
        # Drain completed chunks from the front (preserves order)
        while pending_chunks and pending_chunks[0][0].done():
            task, chunk_aggs, t0 = pending_chunks.popleft()
            labeled_list = task.result()
            latency = time.time() - t0
            
            # Emit each label
            for labeled in labeled_list:
                if not labeled.get("text"):
                    continue  # Skip empty labels
                    
                label_count += 1
                text_preview = labeled["text"][:80] if labeled.get("text") else "(empty)"
                print(f"[label] labeled action #{label_count}: {text_preview}... ({latency:.2f}s, pending_chunks={len(pending_chunks)})")
                
                # Always add to inference buffer
                inference_buffer.append(labeled)
                
                # Only feed training data when sleepwalk is NOT active
                if not sleepwalk_active.is_set():
                    label_queue.put(labeled)
                
                # Wandb logging
                if wandb and wandb.run is not None:
                    log = {
                        "pipeline/labels_total": label_count,
                        "pipeline/chunk_latency_s": latency,
                        "pipeline/label_text": wandb.Html(f"<pre>{labeled['text']}</pre>"),
                    }
                    
                    if label_count % 10 == 1 and labeled.get("img") is not None:
                        log["pipeline/label_image"] = wandb.Image(
                            labeled["img"], caption=labeled["text"][:200],
                        )
                    
                    wandb.log(log)
    
    print(f"[label] finished: {label_count} labels, {chunk_count} chunks, {skip_count} skipped")

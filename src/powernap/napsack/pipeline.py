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


def label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active,
               flush_request=None, flush_complete=None):
    """Label incoming screen recordings by accumulating into video chunks."""
    asyncio.run(_async_label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active,
                                   flush_request, flush_complete))


async def _async_label_loop(recorder, labeler, retriever, label_queue, inference_buffer, sleepwalk_active,
                            flush_request=None, flush_complete=None):
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
    
    # Track flush task specifically for signaling completion
    flush_task = None
    
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
        
        # Handle flush request from inference
        if flush_request is not None and flush_request.is_set():
            flush_request.clear()  # Clear immediately to avoid re-triggering
            
            if chunk_buffer:
                # Submit partial chunk for immediate labeling
                chunk_count += 1
                print(f"[label] flush requested: submitting partial chunk #{chunk_count} with {len(chunk_buffer)} aggregations")
                task = asyncio.create_task(labeler.alabel_chunk(chunk_buffer.copy()))
                pending_chunks.append((task, chunk_buffer.copy(), time.time()))
                flush_task = task  # Track this specific task
                chunk_buffer.clear()
            elif flush_complete is not None:
                # Nothing to flush — signal complete immediately
                flush_complete.set()
        
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
            try:
                labeled_list = task.result()
            except Exception as e:
                logger.warning(f"Label chunk failed: {e}. Skipping chunk.")
                continue
            latency = time.time() - t0
            
            # Check if this was the flush task
            if flush_task is not None and task is flush_task:
                if flush_complete is not None:
                    flush_complete.set()
                flush_task = None  # Clear reference to avoid memory leak
            
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
    
    # On loop exit, ensure any waiting inference thread is unblocked
    if flush_complete is not None:
        flush_complete.set()
    
    print(f"[label] finished: {label_count} labels, {chunk_count} chunks, {skip_count} skipped")

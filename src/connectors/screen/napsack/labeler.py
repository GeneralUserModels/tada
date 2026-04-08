"""Image-based labeler using napsack's Gemini client."""

import asyncio
import contextlib
import json
import os
import sys
import tempfile
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import List, Optional

from PIL import Image

# Import from pack
from napsack.label.clients.litellm import LiteLLMClient
from napsack.label.clients.client import DENSE_IMAGE_CAPTION_SCHEMA
from napsack.label.models import Aggregation as LabelAggregation
from napsack.record.sanitize import sanitize_records

logger = logging.getLogger(__name__)



def _get_pil_image(processed_agg) -> Optional[Image.Image]:
    """Get PIL Image from ProcessedAggregation's in-memory BufferImage."""
    if processed_agg.screenshot is None:
        return None
    return Image.fromarray(processed_agg.screenshot.data)


def _agg_to_dict(processed_agg) -> dict:
    """Convert ProcessedAggregation to dict for sanitization."""
    req = processed_agg.request
    return {
        "timestamp": req.timestamp,
        "end_timestamp": req.end_timestamp,
        "reason": req.reason,
        "event_type": req.event_type,
        "request_state": req.request_state,
        "screenshot_path": req.screenshot_path,
        "screenshot_timestamp": req.screenshot_timestamp,
        "end_screenshot_timestamp": req.end_screenshot_timestamp,
        "monitor": req.monitor,
        "burst_id": req.burst_id,
        "scale_factor": req.scale_factor,
        "events": processed_agg.events,
    }


def _to_label_agg(agg_dict: dict) -> LabelAggregation:
    """Convert aggregation dict to pack's LabelAggregation."""
    return LabelAggregation.from_dict(agg_dict)


class Labeler:
    """Image-based labeler: sends individual frames to Gemini for captioning."""

    def __init__(
        self,
        max_workers: int = 4,
        log_dir: Optional[str] = None,
        save_screenshots: bool = True,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """
        Args:
            max_workers: Number of parallel chunk processors.
            log_dir: Directory to save labels.jsonl and screenshots.
            save_screenshots: If True, save screenshots for labeled samples.
            model: Gemini model name for labeling (default: gemini-3.1-flash-lite-preview).
        """
        self.max_workers = max_workers
        resolved_api_key = api_key or os.environ.get("TADA_LABEL_API_KEY") or None
        with contextlib.redirect_stdout(sys.stderr):
            self.client = LiteLLMClient(model_name=model or "gemini/gemini-3.1-flash-lite-preview", api_key=resolved_api_key)
        self.prompt = self._load_prompt()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.save_screenshots = save_screenshots
        
        self.labels_file = None
        self.screenshots_dir = None
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            self.labels_file = log_path / "labels.jsonl"
            if save_screenshots:
                self.screenshots_dir = log_path / "labeled_screenshots"
                self.screenshots_dir.mkdir(exist_ok=True)

    def _load_prompt(self) -> str:
        """Load the default prompt from pack's label module with dense output format."""
        base = (files("napsack.label") / "prompts" / "default.txt").read_text()
        output_fmt = (files("napsack.label") / "prompts" / "output" / "dense_image.txt").read_text()
        return base.replace("{{OUTPUT_FORMAT}}", output_fmt)

    def label_chunk(self, aggregations: List) -> List[dict]:
        """Label a chunk of aggregations via video.
        
        Args:
            aggregations: List of ProcessedAggregation objects.
            
        Returns:
            List of label dicts, one per aggregation in the input.
        """
        if not aggregations:
            return []
        
        with tempfile.TemporaryDirectory(prefix="video_chunk_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            screenshots_dir = tmpdir_path / "screenshots"
            screenshots_dir.mkdir()
            
            # 1. Extract screenshots and build agg dicts
            valid_aggs = []
            agg_dicts = []
            image_paths = []
            for idx, agg in enumerate(aggregations):
                img = _get_pil_image(agg)
                if img is not None:
                    # Save to temp file for ffmpeg (create_video needs file paths)
                    img_path = screenshots_dir / f"{idx:06d}.png"
                    img.save(img_path, format="PNG")
                    valid_aggs.append(agg)
                    agg_dicts.append(_agg_to_dict(agg))
                    image_paths.append(img_path)
            
            if not image_paths:
                logger.warning("No valid screenshots in chunk")
                return []
            
            # 2. Sanitize: redistribute events to correct time windows
            sanitized_dicts = sanitize_records(agg_dicts, verbose=False)
            
            # 3. Build per-frame event logs
            prompt_lines = []
            for idx, agg_dict in enumerate(sanitized_dicts):
                label_agg = _to_label_agg(agg_dict)
                prompt_lines.append(label_agg.to_prompt(f"Frame {idx + 1}"))

            base_prompt = self.prompt.replace("{{LOGS}}", "")

            # 4. Upload images directly (no video encoding)
            with contextlib.redirect_stdout(sys.stderr):
                file_desc = self.client.upload_images(
                    [str(p) for p in image_paths],
                    per_frame_text=prompt_lines,
                )

            # 5. Generate captions (infinite retry on failure)
            while True:
                try:
                    with contextlib.redirect_stdout(sys.stderr):
                        result = self.client.generate(base_prompt, file_desc, schema=DENSE_IMAGE_CAPTION_SCHEMA)
                    break
                except Exception as e:
                    logger.warning(f"Gemini generate failed: {e}. Retrying in 120s...")
                    time.sleep(120)

            captions = result["actions"]
            dense_caption = result.get("dense_caption", "")

            # 6. Match captions to aggregations (with sanitized events)
            return self._match_captions_to_aggs(captions, valid_aggs, sanitized_dicts, dense_caption)

    async def alabel_chunk(self, aggregations: List) -> List[dict]:
        """Async version of label_chunk - runs in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.label_chunk, aggregations)

    def _match_captions_to_aggs(
        self,
        captions: List[dict],
        aggregations: List,
        sanitized_dicts: List[dict],
        dense_caption: str = "",
    ) -> List[dict]:
        """Match timestamped captions back to source aggregations.
        
        Each caption covers a time range. We assign the caption to the LAST
        aggregation in that range (when the action completed), combining all
        events from the range into that single label.
        """
        results = []
        assigned = set()
        
        for caption in captions:
            start_idx = caption.get("start", 1) - 1
            end_idx = caption.get("end", caption.get("start", 1)) - 1
            
            # Clamp to valid range
            start_idx = max(0, min(start_idx, len(aggregations) - 1))
            end_idx = max(start_idx, min(end_idx, len(aggregations) - 1))
            
            # Skip if already assigned
            if end_idx in assigned:
                continue
            assigned.add(end_idx)
            
            # Use the last aggregation (when action completed) for the screenshot
            agg = aggregations[end_idx]
            ts = agg.request.timestamp
            start_time = datetime.fromtimestamp(ts).strftime("%Y-%m-%d_%H-%M-%S-%f")
            
            # Get PIL image from the final frame
            img = _get_pil_image(agg)
            
            # Save screenshot to disk if enabled (only for labeled samples)
            screenshot_path = None
            if self.screenshots_dir and img is not None:
                screenshot_path = self.screenshots_dir / f"{start_time}.png"
                img.save(screenshot_path, format="PNG")
            
            # Combine events from ALL aggregations in the range
            combined_events = []
            for idx in range(start_idx, end_idx + 1):
                sanitized = sanitized_dicts[idx] if idx < len(sanitized_dicts) else {}
                events = sanitized.get("events", aggregations[idx].events if idx < len(aggregations) else [])
                combined_events.extend(events)
            
            result = {
                "text": caption.get("caption", ""),
                "dense_caption": dense_caption,
                "start_time": start_time,
                "img": img,
                "screenshot_path": str(screenshot_path) if screenshot_path else None,
                "raw_events": combined_events,
            }
            results.append(result)
            
            # Log to file
            if self.labels_file:
                serializable = {
                    "text": result["text"],
                    "dense_caption": result["dense_caption"],
                    "start_time": result["start_time"],
                    "screenshot_path": result["screenshot_path"],
                    "raw_events": result["raw_events"],
                }
                with open(self.labels_file, "a") as f:
                    json.dump(serializable, f, default=str)
                    f.write("\n")
        
        # Unassigned aggregations are dropped - no meaningful activity to describe
        return results

"""Video-based labeler using pack's Gemini client and video utilities."""

import asyncio
import json
import tempfile
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import List, Optional

from PIL import Image

# Import from pack
from label.video import create_video
from label.clients.gemini import GeminiClient
from label.clients.client import CAPTION_SCHEMA
from label.models import Aggregation as LabelAggregation
from record.sanitize import sanitize_records

logger = logging.getLogger(__name__)


def _parse_mmss(time_str: str) -> int:
    """Parse MM:SS format to seconds."""
    try:
        parts = time_str.split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, AttributeError):
        pass
    return 0


def _extract_screenshot(processed_agg, output_path: Path) -> bool:
    """Extract screenshot from aggregation to file. Returns True if successful."""
    # Try in-memory screenshot first
    if processed_agg.screenshot is not None:
        try:
            img_array = processed_agg.screenshot.screenshot
            img = Image.fromarray(img_array)
            img.save(output_path, format="JPEG", quality=85)
            return True
        except Exception:
            pass
    
    # Fall back to copying from file path
    screenshot_path = processed_agg.request.screenshot_path
    if screenshot_path and Path(screenshot_path).exists():
        try:
            img = Image.open(screenshot_path)
            img.save(output_path, format="JPEG", quality=85)
            return True
        except Exception:
            pass
    
    return False


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
    """Video-based labeler using pack's Gemini client and video utilities.
    
    Accumulates screenshots into video chunks and labels them via Gemini Files API
    for higher-quality temporal labels.
    """

    def __init__(
        self,
        chunk_size: int = 60,
        fps: int = 1,
        max_workers: int = 4,
        log_dir: Optional[str] = None,
    ):
        """
        Args:
            chunk_size: Number of screenshots per video chunk (API param).
            fps: Video encoding framerate (1 = one frame per second).
            max_workers: Number of parallel chunk processors.
            log_dir: Directory to save labels.jsonl.
        """
        self.chunk_size = chunk_size
        self.fps = fps
        self.max_workers = max_workers
        self.client = GeminiClient()
        self.prompt = self._load_prompt()
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
        self.labels_file = None
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            self.labels_file = log_path / "labels.jsonl"

    def _load_prompt(self) -> str:
        """Load the default prompt from pack's label module."""
        return (files("label") / "prompts" / "default.txt").read_text()

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
                img_path = screenshots_dir / f"{idx:06d}.jpg"
                if _extract_screenshot(agg, img_path):
                    valid_aggs.append(agg)
                    agg_dicts.append(_agg_to_dict(agg))
                    image_paths.append(img_path)
            
            if not image_paths:
                logger.warning("No valid screenshots in chunk")
                return []
            
            # 2. Sanitize: redistribute events to correct time windows
            sanitized_dicts = sanitize_records(agg_dicts, verbose=False)
            
            # 3. Build prompt with sanitized event logs
            prompt_lines = []
            for idx, agg_dict in enumerate(sanitized_dicts):
                time_str = f"{idx // 60:02}:{idx % 60:02}"
                label_agg = _to_label_agg(agg_dict)
                prompt_lines.append(label_agg.to_prompt(time_str))
            
            full_prompt = self.prompt.replace("{{LOGS}}", "".join(prompt_lines))
            
            # 3. Create video
            video_path = tmpdir_path / "chunk.mp4"
            create_video(
                image_paths=image_paths,
                output_path=video_path,
                fps=self.fps,
                pad_to=None,
                annotate=False,
                aggregations=None,
                session_dir=None,
            )
            
            # 4. Upload to Gemini
            file_desc = self.client.upload_file(str(video_path))
            
            try:
                # 5. Generate captions
                response = self.client.generate(full_prompt, file_desc, schema=CAPTION_SCHEMA)
                captions = response.json if not callable(response.json) else response.json()
            finally:
                # 6. Delete file from Gemini (cleanup quota)
                try:
                    self.client.client.files.delete(name=file_desc.name)
                except Exception as e:
                    logger.debug(f"Failed to delete Gemini file: {e}")
            
            # 7. Match captions to aggregations (with sanitized events)
            return self._match_captions_to_aggs(captions, valid_aggs, sanitized_dicts)

    async def alabel_chunk(self, aggregations: List) -> List[dict]:
        """Async version of label_chunk - runs in thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.label_chunk, aggregations)

    def _match_captions_to_aggs(
        self,
        captions: List[dict],
        aggregations: List,
        sanitized_dicts: List[dict],
    ) -> List[dict]:
        """Match timestamped captions back to source aggregations.
        
        Each caption covers a time range. We assign the caption to the LAST
        aggregation in that range (when the action completed), combining all
        events from the range into that single label.
        """
        results = []
        assigned = set()
        
        for caption in captions:
            start_idx = _parse_mmss(caption.get("start", "00:00")) * self.fps
            end_idx = _parse_mmss(caption.get("end", caption.get("start", "00:00"))) * self.fps
            
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
            
            # Get image from the final frame
            img = None
            if agg.screenshot is not None:
                try:
                    img = Image.fromarray(agg.screenshot.screenshot)
                except Exception:
                    pass
            if img is None:
                img = agg.request.screenshot_path
            
            # Combine events from ALL aggregations in the range
            combined_events = []
            for idx in range(start_idx, end_idx + 1):
                sanitized = sanitized_dicts[idx] if idx < len(sanitized_dicts) else {}
                events = sanitized.get("events", aggregations[idx].events if idx < len(aggregations) else [])
                combined_events.extend(events)
            
            result = {
                "text": caption.get("caption", ""),
                "start_time": start_time,
                "img": img,
                "raw_events": combined_events,
            }
            results.append(result)
            
            # Log to file
            if self.labels_file:
                serializable = {
                    **result,
                    "img": agg.request.screenshot_path,
                }
                with open(self.labels_file, "a") as f:
                    json.dump(serializable, f, default=str)
                    f.write("\n")
        
        # Unassigned aggregations are dropped - no meaningful activity to describe
        return results

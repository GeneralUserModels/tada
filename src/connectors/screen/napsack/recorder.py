import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from datetime import datetime
from queue import Queue, Empty
from typing import List, Optional

from PIL import Image
from napsack.record.__main__ import ScreenRecorder, get_monitor_dpis, calculate_monitor_scales


# Default DPI for screenshot rescaling (lower = smaller images, fewer tokens)
DEFAULT_TARGET_DPI = 100

## A bit unfortunate that we have some tabracadabra dependenceis here... 
# Flag file created by tabracadabra to suppress aggregation during active streaming
TABRACADABRA_SUPPRESS_FLAG = os.path.join(tempfile.gettempdir(), "tada_tab_active")

# Latest frame from napsack screenshot loop (atomic PNG) for Tabracadabra — same process as screen MCP only
TABRACADABRA_LATEST_FRAME_PNG = os.path.join(tempfile.gettempdir(), "tada_tab_latest.png")

# Default event types to disable for online recording (mouse move is too noisy)
DEFAULT_DISABLE = ["move"]


class OnlineRecorder(ScreenRecorder):

    DEFAULT_LOG_DIR = Path(__file__).resolve().parents[4] / "logs"

    def __init__(
        self,
        *args,
        queue_maxsize=0,
        log_dir=None,
        target_dpi=DEFAULT_TARGET_DPI,
        save_screenshots=False,
        disable: Optional[List[str]] = None,
        **kwargs
    ):
        """
        Initialize the online recorder.

        Args:
            queue_maxsize: Max size of aggregation queue (0 = unlimited)
            log_dir: Directory to save logs to
            target_dpi: Target DPI for screenshots (lower = smaller images)
            save_screenshots: If True, save screenshots to disk
            disable: List of event types to disable. Defaults to ["move"].
                     Valid values: "move", "scroll", "click", "key"
                     Pass empty list [] to enable all event types.
        """
        # Calculate scale from target DPI if not explicitly provided
        if "scale" not in kwargs and target_dpi is not None:
            monitor_dpis = get_monitor_dpis()
            if monitor_dpis:
                kwargs["scale"] = calculate_monitor_scales(target_dpi, monitor_dpis)

        # Default to NOT saving screenshots (for tinker usage)
        kwargs.setdefault("save_screenshots", save_screenshots)
        
        # Default to disabling mouse move events (too noisy for online training)
        if disable is None:
            disable = DEFAULT_DISABLE
        kwargs["disable"] = disable
        
        with redirect_stdout(sys.stderr):
            super().__init__(*args, **kwargs)
        self.aggregation_queue = Queue(maxsize=queue_maxsize)

        # always redirect session_dir into logs (or custom log_dir)
        base = Path(log_dir) if log_dir else self.DEFAULT_LOG_DIR
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = base / f"session_{timestamp}"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.save_worker.session_dir = self.session_dir
        self.save_worker.screenshots_dir = self.session_dir / "screenshots"
        self.save_worker.screenshots_dir.mkdir(exist_ok=True)
        self.save_worker.input_log = self.session_dir / "input_events.jsonl"
        self.save_worker.screenshot_log = self.session_dir / "screenshots.jsonl"
        self.aggregation_worker.aggregations_file = self.session_dir / "raw_aggregations.jsonl"
        self.input_event_queue.session_dir = self.session_dir

        self.image_queue.add_callback(self._publish_latest_frame_png)

    def _publish_latest_frame_png(self, buffer_image) -> None:
        """Write each new frame to a temp path for Tabracadabra (main process reads; avoids second mss)."""
        try:
            data = getattr(buffer_image, "data", None)
            if data is None:
                return
            img = Image.fromarray(data)
            tmp = TABRACADABRA_LATEST_FRAME_PNG + ".tmp"
            img.save(tmp, format="PNG")
            os.replace(tmp, TABRACADABRA_LATEST_FRAME_PNG)
        except Exception:
            pass

    def start(self):
        with redirect_stdout(sys.stderr):
            super().start()

    def _on_aggregation_request(self, request):
        if not request:
            return

        if os.path.exists(TABRACADABRA_SUPPRESS_FLAG):
            return

        processed = self.aggregation_worker.process_aggregation(request)

        with redirect_stdout(sys.stderr):
            if self.processed_aggregations == 0:
                print("-------------------------------------------------------------------")
                print(">>>>                    Aggregation Summary                    <<<<")
                print(f">>>> Session Directory: {str(self.session_dir.name):37s} <<<<")
                print("-------------------------------------------------------------------")
                print("Screenshot | # Events |     Timestamp     | Capture Reason ")
                print("-------------------------------------------------------------------")

            screenshot_status = "Y" if processed.screenshot else "N"
            print(f"     {screenshot_status}     | {str(len(processed.events)):8s} |"
                  f"{str(processed.request.timestamp):<18} | {processed.request.reason}")

        self.aggregation_queue.put(processed)
        self.processed_aggregations += 1

    def iter_aggregations(self):
        while self.running:
            try:
                yield self.aggregation_queue.get(timeout=1.0)
            except Empty:
                continue

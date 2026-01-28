import asyncio
from pathlib import Path
from datetime import datetime
from queue import Queue, Empty

from record.__main__ import ScreenRecorder


class OnlineRecorder(ScreenRecorder):

    DEFAULT_LOG_DIR = Path(__file__).resolve().parents[4] / "logs"

    def __init__(self, *args, queue_maxsize=0, log_dir=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.aggregation_queue = Queue(maxsize=queue_maxsize)

        # always redirect session_dir into powernap/logs (or custom log_dir)
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

    def _on_aggregation_request(self, request):
        if not request:
            return

        processed = self.aggregation_worker.process_aggregation(request)

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

    async def async_iter_aggregations(self):
        loop = asyncio.get_event_loop()
        while self.running:
            try:
                agg = await loop.run_in_executor(None, self.aggregation_queue.get, True, 1.0)
                yield agg
            except Empty:
                continue

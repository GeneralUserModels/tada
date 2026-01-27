import base64
import json
import re
from datetime import datetime
from pathlib import Path

from litellm import completion as litellm_completion
from label.models import Aggregation as LabelAggregation


LABEL_PROMPT = """You are an expert at describing user actions from a screenshot and input event logs.

Describe **exactly what the user did** in this screenshot. Use both the visual information and the input event logs below.

## Input Events

{{LOGS}}

## Rules

1. Fully reconstruct any typed text or commands — state the entire string.
2. Each caption must cover exactly one user interaction.
3. Name all objects interacted with (files, UI elements, buttons, etc.) using their visible labels.
4. Ignore coordinates and raw keycodes — describe actions in human terms.
5. Favor the screenshot over input events when they conflict.
6. Merge repeated identical actions into one.
7. Use past tense.

## Examples

- Opened the System Settings application.
- Typed "openai office munich" into the Google search bar and pressed Enter.
- Clicked on the Google search result titled "Vegan chocolate cake recipes"
- Ran "cd /home/user/projects/gs-utils" in the terminal.
- Clicked the "Downloads" folder in the sidebar.

## Output

A JSON array:
```json
[{"caption": "..."}]
```"""


class Labeler:

    def __init__(self, model="gemini/gemini-2.0-flash", log_dir=None):
        self.model = model
        self.labels_file = None
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            self.labels_file = log_path / "labels.jsonl"

    def label(self, processed_agg):
        label_agg = self._to_label_agg(processed_agg)
        events_text = label_agg.to_prompt("00:00")
        prompt = LABEL_PROMPT.replace("{{LOGS}}", events_text)

        content = []
        screenshot_path = processed_agg.request.screenshot_path
        if screenshot_path and Path(screenshot_path).exists():
            b64 = base64.b64encode(Path(screenshot_path).read_bytes()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        content.append({"type": "text", "text": prompt})

        response = litellm_completion(
            model=self.model,
            messages=[{"role": "user", "content": content}],
        )

        captions = self._parse_response(response.choices[0].message.content)

        ts = processed_agg.request.timestamp
        start_time = datetime.fromtimestamp(ts).strftime("%Y-%m-%d_%H-%M-%S-%f")

        result = {
            "text": captions[0]["caption"] if captions else "",
            "start_time": start_time,
            "img": screenshot_path,
            "raw_events": processed_agg.events,
        }

        if self.labels_file:
            with open(self.labels_file, "a") as f:
                json.dump(result, f)
                f.write("\n")

        return result

    def iter_labeled(self, recorder):
        for agg in recorder.iter_aggregations():
            yield self.label(agg)

    async def async_iter_labeled(self, recorder):
        async for agg in recorder.async_iter_aggregations():
            yield self.label(agg)

    def _to_label_agg(self, processed_agg):
        req = processed_agg.request
        flat = {
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
        return LabelAggregation.from_dict(flat)

    def _parse_response(self, text):
        if not text:
            return []

        # try to extract JSON from markdown code block
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            text = match.group(1).strip()

        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        # fallback: treat the whole response as a single caption
        return [{"caption": text.strip()}]

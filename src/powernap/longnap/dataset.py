import os
import random
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from torch.utils.data import Dataset
from datasets import load_dataset, load_from_disk
from PIL import ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True


class NAPSack(Dataset):

    def __init__(
        self,
        raw_dataset: Dataset,
        past_len: int = 3,
        future_len: int = 2,
        stride: int = 1,
        system_message: str = None,
        split: str = None,
        num_imgs_per_sample: int = 0,
        include_timestamps: bool = False,
        timestamp_format: str = "nice",
        processor=None,
    ):
        self.past_len = past_len
        self.future_len = future_len
        self.stride = stride
        self.num_imgs_per_sample = num_imgs_per_sample
        self.include_timestamps = include_timestamps
        self.timestamp_format = timestamp_format.lower()
        self.processor = processor

        self.system_message = system_message
        self.raw_dataset = raw_dataset[split]

        self.valid_indices = self._calculate_valid_indices()

    def _calculate_valid_indices(self) -> List[int]:
        valid_indices = []
        dataset_len = len(self.raw_dataset)
        min_required = self.past_len + self.future_len

        for i in range(0, dataset_len - min_required + 1, self.stride):
            valid_indices.append(i)
        return valid_indices

    def __len__(self) -> int:
        return len(self.valid_indices)

    def __getitem__(self, idx: int) -> List[Dict[str, Any]]:
        """
        Get a formatted sample with sliding window structure.

        Returns:
            List of messages in the format expected by the chat template
        """

        start_idx = self.valid_indices[idx]
        messages = []

        if self.system_message:
            messages.append({
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": self.system_message
                    }
                ],
            })

        task_description = "You will analyze user behavior and predict what the user will do next. Below are the actions the user took" + \
            ("." if self.num_imgs_per_sample == 0 else ". Look at the images of their device to help you predict the user's next action.")
        
        all_images = []
        image_content = []
        past_actions_list = []

        for i in range(self.past_len):
            sample_idx = start_idx + i
            sample = self.raw_dataset[sample_idx]

            if self.num_imgs_per_sample > 0:
                if self.num_imgs_per_sample is None or i >= (self.past_len - self.num_imgs_per_sample):
                    # Load image from path
                    img = sample["img"]
                    image_content.append({"type": "image", "image": img})
                    all_images.append(img)

            past_actions_list.append(self._fmt_text(sample))

        # Build past actions block with consistent formatting
        past_actions_block = "<actions>\n" + "\n".join("    " + a for a in past_actions_list) + "\n</actions>"
        
        # Build content: images first, then task description, then past actions
        all_content = image_content + [
            {"type": "text", "text": task_description + "\n\n" + past_actions_block}
        ]

        messages.append({
            "role": "user",
            "content": all_content
        })

        assistant_response = "<actions>\n"
        for i in range(self.future_len):
            sample_idx = start_idx + self.past_len + i
            sample = self.raw_dataset[sample_idx]
            # just some indent
            assistant_response += "    " + self._fmt_text(sample) + "\n"
        assistant_response += "</actions>"

        messages.append({
            "role": "assistant",
            "content": [
                {"type": "text", "text": assistant_response.strip()}
            ]
        })

        ret_obj = {}

        text = self.processor.apply_chat_template(
            messages[:-1],
            add_generation_prompt=False,
            tokenize=False,
        )

        ret_obj = {
            "prompt": text,
            "solution": messages[-1]["content"][0]["text"],
        }


        # add images only if we have them-
        if self.num_imgs_per_sample > 0:
            ret_obj["images"] = all_images

        ret_obj["future_len"] = self.future_len
        ret_obj["past_len"] = self.past_len
        # Convert timestamp string to Unix timestamp (like time.time())
        start_time_str = self.raw_dataset[start_idx]["start_time"]
        start_dt = self._ts(start_time_str)
        ret_obj["ts"] = start_dt.timestamp()
        
        # End timestamp (last future action) - for retrieval visibility
        end_idx = start_idx + self.past_len + self.future_len - 1
        end_time_str = self.raw_dataset[end_idx]["start_time"]
        ret_obj["end_ts"] = self._ts(end_time_str).timestamp()
        
        ret_obj["actions"] = assistant_response
        ret_obj["past_actions"] = past_actions_block
        ret_obj["prompt_id"] = idx

        return ret_obj

    def _ts(self, s: str) -> datetime:
        return datetime.strptime(s, "%Y-%m-%d_%H-%M-%S-%f")

    def _format_timestamp_nice(self, dt: datetime) -> str:
        """
        Format timestamp as "Monday, July 4th - 8:15 AM" with minute-level precision.
        """
        # Snap to the nearest minute (remove seconds and microseconds)
        snapped_dt = dt.replace(second=0, microsecond=0)

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_name = day_names[snapped_dt.weekday()]

        month_names = ["January", "February", "March", "April", "May", "June",
                       "July", "August", "September", "October", "November", "December"]
        month_name = month_names[snapped_dt.month - 1]

        day = snapped_dt.day
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')

        hour = snapped_dt.hour
        if hour == 0:
            hour = 12
            ampm = "AM"
        elif hour < 12:
            ampm = "AM"
        elif hour == 12:
            ampm = "PM"
        else:
            hour -= 12
            ampm = "PM"

        minute_str = f"{snapped_dt.minute:02d}"

        return f"{day_name}, {month_name} {day}{suffix} - {hour}:{minute_str} {ampm}"

    def _fmt_text(self, item: Dict[str, Any]) -> str:
        # TODO: this is cooked, the timestamps might not be in the same timezone as the local device
        # ideally, the model should learn to read the screenshot for the time-
        if self.include_timestamps and self.timestamp_format != "none":
            if self.timestamp_format == "nice":
                start_dt = self._ts(item['start_time'])
                start_formatted = self._format_timestamp_nice(start_dt)
                return f"<action>[ {start_formatted} ] {item['text']}</action>"
            else:
                return f"<action>[ {item['start_time']} ] {item['text']}</action>"
        return f"<action>{item["text"]}</action>"


def create_datasets(
    dataset_path=None,
    past_len: int = 16,
    future_len: int = 16,
    stride: int = 8,
    num_imgs_per_sample: int = 0,
    processor=None,
    include_timestamps: bool = False,
):
    dataset = load_dataset("parquet", data_files=dataset_path)

    dataset_dict = {"train": None, "validation": None, "test": None}
    for split in dataset_dict.keys():
        if split not in dataset:
            print(f"Warning: Split '{split}' not found in dataset.")
            continue
        dataset_dict[split] = NAPSack(
            raw_dataset=dataset,
            past_len=past_len,
            future_len=future_len,
            stride=stride,
            split=split,
            num_imgs_per_sample=num_imgs_per_sample,
            processor=processor,
            include_timestamps=include_timestamps,
        )

    return dataset_dict["train"], dataset_dict["validation"], dataset_dict["test"]

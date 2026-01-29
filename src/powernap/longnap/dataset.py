from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Sequence

import chz
from datasets import load_dataset
from PIL import ImageFile
from torch.utils.data import Dataset

from tinker_cookbook import renderers
from tinker_cookbook.renderers import Renderer, get_renderer
from tinker_cookbook.rl.types import (
    EnvGroupBuilder,
    RLDataset,
    RLDatasetBuilder,
)
from tinker_cookbook.tokenizer_utils import get_tokenizer
from tinker_cookbook.image_processing_utils import get_image_processor

from .trainer_utils import TASK_DESCRIPTION, TASK_DESCRIPTION_WITH_IMAGES

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
    ):
        self.past_len = past_len
        self.future_len = future_len
        self.stride = stride
        self.num_imgs_per_sample = num_imgs_per_sample
        self.include_timestamps = include_timestamps
        self.timestamp_format = timestamp_format.lower()

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

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """
        Get a formatted sample with sliding window structure.

        Returns:
            Dict containing:
                - messages: List of message dicts (user context with images) for the renderer
                - solution: The ground truth assistant response
                - images: List of PIL images (for reference)
                - ts, end_ts, future_len, past_len, past_actions, prompt_id: metadata
        """

        start_idx = self.valid_indices[idx]
        messages = []

        if self.system_message:
            messages.append({
                "role": "system",
                "content": self.system_message,
            })

        task_description = TASK_DESCRIPTION_WITH_IMAGES if self.num_imgs_per_sample > 0 else TASK_DESCRIPTION
        
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
        # For multimodal messages, content is a list of parts
        if image_content:
            all_content = image_content + [
                {"type": "text", "text": task_description + "\n\n" + past_actions_block}
            ]
        else:
            # For text-only, content can be a simple string
            all_content = task_description + "\n\n" + past_actions_block

        messages.append({
            "role": "user",
            "content": all_content
        })

        # Build the ground truth solution
        assistant_response = "<actions>\n"
        for i in range(self.future_len):
            sample_idx = start_idx + self.past_len + i
            sample = self.raw_dataset[sample_idx]
            assistant_response += "    " + self._fmt_text(sample) + "\n"
        assistant_response += "</actions>"

        # Build return object with messages (not pre-rendered text)
        ret_obj = {
            "messages": messages,  # Messages for renderer (context only, no solution)
            "solution": assistant_response.strip(),
            "images": all_images if all_images else None,
            "future_len": self.future_len,
            "past_len": self.past_len,
            "past_actions": past_actions_block,
            "prompt_id": idx,
        }

        # Convert timestamp string to Unix timestamp (like time.time())
        start_time_str = self.raw_dataset[start_idx]["start_time"]
        start_dt = self._ts(start_time_str)
        ret_obj["ts"] = start_dt.timestamp()
        
        # End timestamp (last future action) - for retrieval visibility
        end_idx = start_idx + self.past_len + self.future_len - 1
        end_time_str = self.raw_dataset[end_idx]["start_time"]
        ret_obj["end_ts"] = self._ts(end_time_str).timestamp()

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
    include_timestamps: bool = False,
):
    """
    Create train/validation/test datasets.
    
    Note: processor parameter removed - the renderer in the trainer handles tokenization.
    """
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
            include_timestamps=include_timestamps,
        )

    return dataset_dict["train"], dataset_dict["validation"], dataset_dict["test"]


# =============================================================================
# RL Dataset wrappers for tinker_cookbook training loop
# =============================================================================

@dataclass(frozen=True)
class LongNAPRLDataset(RLDataset):
    """
    RL Dataset wrapper for LongNAP training.
    
    Wraps a NAPSack dataset and produces EnvGroupBuilders for the 
    tinker_cookbook RL training loop.
    """
    
    napsack: NAPSack
    renderer: Renderer
    tokenizer: Any
    retriever: Any  # InMemoryBM25Temporal, but avoiding circular import
    reward_scorer: Callable
    batch_size: int
    group_size: int
    retrieval_top_k: int = 10
    retrieval_mmr_k: int = 10
    retrieval_mmr_alpha: float = 0.5
    retrieval_time_decay_lambda: float = 0.5
    
    def get_batch(self, index: int) -> Sequence[EnvGroupBuilder]:
        """
        Get a batch of EnvGroupBuilders for training.
        
        Args:
            index: Batch index
            
        Returns:
            List of EnvGroupBuilder instances, one per sample in the batch
        """
        # Import here to avoid circular import
        from .env import LongNAPEnvGroupBuilder
        
        builders = []
        for i in range(self.batch_size):
            sample_idx = index * self.batch_size + i
            if sample_idx >= len(self.napsack):
                break
            
            input_data = self.napsack[sample_idx]
            builder = LongNAPEnvGroupBuilder(
                input_data=input_data,
                renderer=self.renderer,
                tokenizer=self.tokenizer,
                retriever=self.retriever,
                reward_scorer=self.reward_scorer,
                num_envs=self.group_size,
                retrieval_top_k=self.retrieval_top_k,
                retrieval_mmr_k=self.retrieval_mmr_k,
                retrieval_mmr_alpha=self.retrieval_mmr_alpha,
                retrieval_time_decay_lambda=self.retrieval_time_decay_lambda,
            )
            builders.append(builder)
        
        return builders
    
    def __len__(self) -> int:
        """Return the number of batches in the dataset."""
        return len(self.napsack) // self.batch_size


@chz.chz
class LongNAPDatasetBuilder(RLDatasetBuilder):
    """
    Builder for LongNAP RL datasets.
    
    Initializes all shared resources (renderer, retriever, reward scorer)
    and creates train/test datasets.
    """
    
    # Model configuration
    model_name: str
    renderer_name: str | None = None
    
    # Dataset configuration
    dataset_path: str
    past_len: int = 16
    future_len: int = 16
    stride: int = 8
    num_imgs_per_sample: int = 0
    include_timestamps: bool = False
    
    # Training configuration
    batch_size: int = 2
    group_size: int = 8
    
    # Retrieval configuration
    retrieval_top_k: int = 10
    retrieval_mmr_k: int = 10
    retrieval_mmr_alpha: float = 0.5
    retrieval_time_decay_lambda: float = 0.5
    dedup_threshold: float = 0.8
    
    # Reward configuration
    reward_llm: str = "gemini/gemini-3-flash-preview"
    reward_scorer: Callable | None = None  # If None, creates one using reward_llm
    
    async def __call__(self) -> tuple[RLDataset, RLDataset | None]:
        """
        Build the train and test RL datasets.
        
        Returns:
            Tuple of (train_dataset, test_dataset) or (train_dataset, None)
        """
        from .retrievers import InMemoryBM25Temporal, jaccard_ngrams
        from .scorer import create_reward_scorer
        from tinker_cookbook import model_info
        
        # Get renderer name if not specified
        renderer_name = self.renderer_name
        if renderer_name is None:
            renderer_name = model_info.get_recommended_renderer_name(self.model_name)
        
        # Create tokenizer and renderer
        tokenizer = get_tokenizer(self.model_name)
        
        image_processor = get_image_processor(self.model_name)
        renderer = get_renderer(renderer_name, tokenizer, image_processor)
        
        # Create retriever
        def dedup_fn(a, b):
            return jaccard_ngrams(a, b, n=3)
        
        retriever = InMemoryBM25Temporal(
            dedup_threshold=self.dedup_threshold,
            dedup_sim_fn=dedup_fn,
        )
        
        # Create NAPSack datasets
        train_napsack, val_napsack, test_napsack = create_datasets(
            dataset_path=self.dataset_path,
            past_len=self.past_len,
            future_len=self.future_len,
            stride=self.stride,
            num_imgs_per_sample=self.num_imgs_per_sample,
            include_timestamps=self.include_timestamps,
        )
        
        # Create reward scorer if not provided
        reward_scorer = self.reward_scorer
        if reward_scorer is None:
            reward_scorer = create_reward_scorer(reward_llm=self.reward_llm)
        
        # Create train dataset
        train_dataset = None
        if train_napsack is not None:
            train_dataset = LongNAPRLDataset(
                napsack=train_napsack,
                renderer=renderer,
                tokenizer=tokenizer,
                retriever=retriever,
                reward_scorer=reward_scorer,
                batch_size=self.batch_size,
                group_size=self.group_size,
                retrieval_top_k=self.retrieval_top_k,
                retrieval_mmr_k=self.retrieval_mmr_k,
                retrieval_mmr_alpha=self.retrieval_mmr_alpha,
                retrieval_time_decay_lambda=self.retrieval_time_decay_lambda,
            )
        
        # Create test dataset (use validation or test split)
        test_dataset = None
        test_napsack_to_use = test_napsack or val_napsack
        if test_napsack_to_use is not None:
            test_dataset = LongNAPRLDataset(
                napsack=test_napsack_to_use,
                renderer=renderer,
                tokenizer=tokenizer,
                retriever=retriever,
                reward_scorer=reward_scorer,
                batch_size=len(test_napsack_to_use),  # Single batch for test
                group_size=self.group_size,
                retrieval_top_k=self.retrieval_top_k,
                retrieval_mmr_k=self.retrieval_mmr_k,
                retrieval_mmr_alpha=self.retrieval_mmr_alpha,
                retrieval_time_decay_lambda=self.retrieval_time_decay_lambda,
            )
        
        return train_dataset, test_dataset

import asyncio
import copy
import json
from datetime import datetime
from pathlib import Path

from PIL import Image

import tinker

from user_models.base import BasePredictor
from user_models.powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION, TASK_DESCRIPTION_WITH_IMAGES, build_actions_block,
    build_think_user_message, build_revise_user_message, build_actions_user_message,
    collect_dense_captions,
)
from retrievers import InMemoryBM25Temporal, jaccard_ngrams, mmr_select


class FinetunedPredictor(BasePredictor):

    should_score_prediction = True

    def __init__(self, data_manager=None, renderer=None, tokenizer=None, max_tokens=512,
                 temperature=1.0, retriever=None, retriever_checkpoint=None, log_dir=None,
                 top_k=10, mmr_k=5, mmr_alpha=0.5, time_decay_lambda=0.5,
                 sampling_client=None):
        self.data_manager = data_manager
        self.renderer = renderer
        self.tokenizer = tokenizer
        self.model_path = None  # set by inference loop for logging
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_k = top_k
        self.mmr_k = mmr_k
        self.mmr_alpha = mmr_alpha
        self.time_decay_lambda = time_decay_lambda
        self.sampling_client = sampling_client

        if retriever:
            self.retriever = retriever
        else:
            dedup_fn = lambda a, b: jaccard_ngrams(a, b, n=3)
            self.retriever = InMemoryBM25Temporal(dedup_threshold=0.8, dedup_sim_fn=dedup_fn)

        if retriever_checkpoint:
            self.retriever.load_checkpoint(retriever_checkpoint)

        self.predictions_file = None
        if log_dir:
            log_path = Path(log_dir)
            log_path.mkdir(parents=True, exist_ok=True)
            self.predictions_file = log_path / "predictions.jsonl"

        self._verifier_prompt_path = (
            Path(__file__).resolve().parents[1] / "longnap" / "verifiers" / "accuracy.txt"
        )

    def _sample(self, messages, stop):
        model_input = self.renderer.build_generation_prompt(messages)
        sample_result = asyncio.run(self.sampling_client.sample_async(
            prompt=model_input,
            num_samples=1,
            sampling_params=tinker.SamplingParams(
                stop=stop,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            ),
        ))
        tokens = sample_result.sequences[0].tokens
        return self.tokenizer.decode(tokens, skip_special_tokens=True)

    def predict(self, messages, ts, future_len=4, past_actions="", dense_caption=""):
        """Run the Think → Retrieve → Revise → Actions flow."""
        # 1) Think - merge think instruction into last user message, then sample
        #    Content is always a list (built by predict_from_snapshot), so just append a TextPart.
        messages = copy.deepcopy(messages)
        think_msg = build_think_user_message()
        messages[-1]["content"].append(
            {"type": "text", "text": "\n\n" + think_msg["content"]}
        )

        think_text = self._sample(messages, stop=["</rationale>"])
        messages.append({"role": "assistant", "content": think_text})

        # 2) Retrieve using think output + past actions + dense caption
        query = think_text
        if past_actions:
            query = query + "\n\n" + past_actions
        if dense_caption:
            query = query + "\n\n" + dense_caption

        hits = self.retriever.query(
            query, k=self.top_k, cutoff_ts=int(ts),
            namespaces=["train"], time_decay_lambda=self.time_decay_lambda,
        )
        if hits:
            items = [(h["text"], h["score"], h) for h in hits]
            selected = mmr_select(items, top_m=self.mmr_k, alpha=self.mmr_alpha)
            hits = [it[2] for it in selected]
        retrieved_text = "\n\n".join(h["text"] for h in hits)

        # 3) Revise - add revise instruction with retrieved context and sample
        messages.append(build_revise_user_message(retrieved_text))
        revise_text = self._sample(messages, stop=["</revise>"])
        messages.append({"role": "assistant", "content": revise_text})

        # 4) Actions - add actions instruction and sample
        messages.append(build_actions_user_message(future_len))
        actions_text = self._sample(messages, stop=["</actions>"])

        result = {
            "think": think_text,
            "retrieved": retrieved_text,
            "revise": revise_text,
            "actions": actions_text,
            "timestamp": datetime.now().isoformat(),
            "model_path": self.model_path,
        }

        if self.predictions_file:
            with open(self.predictions_file, "a") as f:
                json.dump(result, f)
                f.write("\n")

        return result

    def predict_from_snapshot(self, past, future_len, num_imgs_per_sample=None, **kwargs):
        """Run prediction from a pre-sliced list of past actions."""
        past_actions_block = build_actions_block(past)

        # Always build content as a list so predict() can append TextParts directly
        actions_with_imgs = past[-num_imgs_per_sample:] if num_imgs_per_sample is not None else past
        image_content = [
            {"type": "image", "image": Image.open(action["img_path"]).convert("RGB")}
            for action in actions_with_imgs if action.get("img_path") is not None
        ]
        if image_content:
            content = image_content + [
                {"type": "text", "text": TASK_DESCRIPTION_WITH_IMAGES + "\n\n" + past_actions_block}
            ]
        else:
            content = [{"type": "text", "text": TASK_DESCRIPTION + "\n\n" + past_actions_block}]

        messages = [{"role": "user", "content": content}]
        ts = past[0]["timestamp"]

        dense_caption = collect_dense_captions(past)
        return self.predict(messages, ts, future_len=future_len, past_actions=past_actions_block, dense_caption=dense_caption)

import base64
import copy
import io
import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from PIL import Image

from litellm import completion as litellm_completion

from user_models.base import BasePredictor
from user_models.powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION, TASK_DESCRIPTION_WITH_IMAGES, build_actions_block,
    build_think_user_message, build_revise_user_message, build_actions_user_message,
)
from retrievers import InMemoryBM25Temporal, jaccard_ngrams, mmr_select


class PromptedPredictor(BasePredictor):
    """Retrieval-augmented next-action predictor using a prompted LLM (no Tinker required).

    Runs the same Think → Retrieve → Revise → Actions multi-turn pipeline as
    FinetunedPredictor, but samples from any LiteLLM-compatible model using plain
    text messages (no Qwen-specific multipart format).
    """

    def __init__(self, data_manager=None, model: str = "", api_key: str = "",
                 max_tokens: int = 512, temperature: float = 1.0, retriever=None,
                 retriever_checkpoint=None, log_dir=None, top_k: int = 10,
                 mmr_k: int = 5, mmr_alpha: float = 0.5, time_decay_lambda: float = 0.5):
        self.data_manager = data_manager
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_k = top_k
        self.mmr_k = mmr_k
        self.mmr_alpha = mmr_alpha
        self.time_decay_lambda = time_decay_lambda

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
            self.predictions_file = log_path / "predictions_prompted.jsonl"

        self._indexed_context_count = 0

        self._verifier_prompt_path = (
            Path(__file__).resolve().parents[1] / "powernap" / "longnap" / "verifiers" / "accuracy.txt"
        )

    @staticmethod
    def _ensure_cache_control(msg: dict) -> dict:
        """Ensure a message has cache_control so LiteLLM treats it as part of a cached block."""
        content = msg.get("content")
        if isinstance(content, str):
            return {**msg, "content": [
                {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
            ]}
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("cache_control"):
                    return msg
            # Add cache_control to the last text part
            parts = list(content)
            for i in range(len(parts) - 1, -1, -1):
                if isinstance(parts[i], dict) and parts[i].get("type") == "text":
                    parts[i] = {**parts[i], "cache_control": {"type": "ephemeral"}}
                    return {**msg, "content": parts}
        return msg

    def _sample(self, messages: list, stop: list) -> str:
        logger.info("[llm] prediction: generating")
        response = litellm_completion(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=stop,
            api_key=self.api_key or None,
            metadata={"app": "tabracadabra"},
        )
        return response.choices[0].message.content or ""

    def predict(self, messages: list, ts, future_len: int = 4, past_actions: str = "") -> dict:
        """Run the Think → Retrieve → Revise → Actions flow using LiteLLM."""
        messages = copy.deepcopy(messages)

        # 1) Think
        messages.append(build_think_user_message())
        think_text = self._sample(messages, stop=["</rationale>"])
        messages.append({"role": "assistant", "content": [
            {"type": "text", "text": think_text, "cache_control": {"type": "ephemeral"}}
        ]})

        # 2) Retrieve using think output + past actions as query
        query = think_text
        if past_actions:
            query = query + "\n\n" + past_actions

        hits = self.retriever.query(
            query, k=self.top_k, cutoff_ts=int(ts),
            namespaces=["context"], time_decay_lambda=self.time_decay_lambda,
        )
        if hits:
            items = [(h["text"], h["score"], h) for h in hits]
            selected = mmr_select(items, top_m=self.mmr_k, alpha=self.mmr_alpha)
            hits = [it[2] for it in selected]
        retrieved_text = "\n\n".join(h["text"] for h in hits)

        # 3) Revise
        messages.append(build_revise_user_message(retrieved_text))
        revise_text = self._sample(messages, stop=["</revise>"])
        messages.append({"role": "assistant", "content": [
            {"type": "text", "text": revise_text, "cache_control": {"type": "ephemeral"}}
        ]})

        # 4) Actions — predict the next N actions
        messages.append(build_actions_user_message(future_len))
        actions_text = self._sample(messages, stop=["</actions>"])
        messages.append({"role": "assistant", "content": [
            {"type": "text", "text": actions_text, "cache_control": {"type": "ephemeral"}}
        ]})

        # Mark every message for caching so tabracadabra can reuse the
        # cached prefix via LiteLLM's Gemini context caching.
        messages = [self._ensure_cache_control(m) for m in messages]

        result = {
            "think": think_text,
            "retrieved": retrieved_text,
            "revise": revise_text,
            "actions": actions_text,
            "messages": messages,
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
        }

        if self.predictions_file:
            with open(self.predictions_file, "a") as f:
                json.dump(result, f)
                f.write("\n")

        return result

    def index_context(self) -> None:
        """Index new context buffer events into the retriever (incremental)."""
        if self.data_manager is None:
            return
        new_events = self.data_manager.buffer[self._indexed_context_count:]
        for event in new_events:
            text = event.get("text")
            if text:
                self.retriever.add(
                    text,
                    event_ts=int(event["timestamp"]),
                    namespace="context",
                )
        self._indexed_context_count = len(self.data_manager.buffer)

    def predict_from_snapshot(self, past: list, future_len: int,
                              num_imgs_per_sample: int | None = None, **kwargs) -> dict:
        """Run prediction from a pre-sliced list of past actions."""
        self.index_context()

        past_actions_block = build_actions_block(past)

        actions_with_imgs = past[-num_imgs_per_sample:] if num_imgs_per_sample is not None else past
        image_parts = []
        for action in actions_with_imgs:
            img_path = action.get("img_path")
            if img_path is not None:
                buf = io.BytesIO()
                Image.open(img_path).save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                image_parts.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                })

        if image_parts:
            content = image_parts + [
                {"type": "text", "text": TASK_DESCRIPTION_WITH_IMAGES + "\n\n" + past_actions_block,
                 "cache_control": {"type": "ephemeral"}}
            ]
        else:
            content = [
                {"type": "text", "text": TASK_DESCRIPTION + "\n\n" + past_actions_block,
                 "cache_control": {"type": "ephemeral"}}
            ]

        messages = [{"role": "user", "content": content}]
        ts = past[0]["timestamp"]
        return self.predict(messages, ts, future_len=future_len, past_actions=past_actions_block)

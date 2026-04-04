import base64
import copy
import io
import json
from datetime import datetime
from pathlib import Path

from PIL import Image

from litellm import completion as litellm_completion

from user_models.base import BasePredictor
from user_models.powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION, TASK_DESCRIPTION_WITH_IMAGES, build_actions_block,
    build_actions_user_message, collect_dense_captions,
)
from retrievers import InMemoryBM25Temporal, jaccard_ngrams, mmr_select


class PromptedPredictor(BasePredictor):
    """Retrieval-augmented next-action predictor using a prompted LLM.

    Retrieves relevant context via BM25, then predicts next actions in a
    single LLM call.  Compatible with any LiteLLM-supported model.
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
        response = litellm_completion(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=stop,
            api_key=self.api_key or None,
        )
        return response.choices[0].message.content or ""

    def predict(self, messages: list, ts, future_len: int = 4, past_actions: str = "", dense_caption: str = "") -> dict:
        """Retrieve context, then predict next actions in a single LLM call."""
        messages = copy.deepcopy(messages)

        # 1) Retrieve using past actions + dense caption as query
        query = past_actions
        if dense_caption:
            query = query + "\n\n" + dense_caption

        hits = self.retriever.query(
            query, k=self.top_k, cutoff_ts=int(ts),
            namespaces=["context"], time_decay_lambda=self.time_decay_lambda,
        )
        if hits:
            items = [(h["text"], h["score"], h) for h in hits]
            selected = mmr_select(items, top_m=self.mmr_k, alpha=self.mmr_alpha)
            hits = [it[2] for it in selected]
        retrieved_text = "\n\n".join(h["text"] for h in hits)

        # 2) Inject retrieved context and ask for actions in one shot
        if retrieved_text:
            context_block = f"<context>\n{retrieved_text}\n</context>\n\n"
            messages.append({"role": "user", "content": [
                {"type": "text",
                 "text": f"Here is some relevant context about this user:\n{context_block}"
                         f"Predict the next {future_len} actions the user will take.",
                 "cache_control": {"type": "ephemeral"}}
            ]})
        else:
            messages.append(build_actions_user_message(future_len))

        actions_text = self._sample(messages, stop=["</actions>"])
        messages.append({"role": "assistant", "content": [
            {"type": "text", "text": actions_text, "cache_control": {"type": "ephemeral"}}
        ]})

        messages = [self._ensure_cache_control(m) for m in messages]

        result = {
            "retrieved": retrieved_text,
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
            text = event.get("text", "")
            dense_caption = event.get("dense_caption", "")
            if dense_caption:
                text = dense_caption.strip() + "\n" + text if text else dense_caption
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

        dense_caption = collect_dense_captions(past)
        return self.predict(messages, ts, future_len=future_len, past_actions=past_actions_block, dense_caption=dense_caption)

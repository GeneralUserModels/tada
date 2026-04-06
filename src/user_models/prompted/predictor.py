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
    collect_dense_captions,
)
from retrievers import InMemoryBM25Temporal, jaccard_ngrams, mmr_select


class PromptedPredictor(BasePredictor):
    """Retrieval-augmented next-action predictor using a prompted LLM.

    Retrieves relevant context via BM25, then predicts next actions in a
    single LLM call.  Compatible with any LiteLLM-supported model.
    """

    def __init__(self, data_manager=None, model: str = "", api_key: str = "",
                 max_tokens: int = 2048, temperature: float = 1.0, retriever=None,
                 retriever_checkpoint=None, log_dir=None, top_k: int = 20,
                 mmr_k: int = 10, mmr_alpha: float = 0.5, time_decay_lambda: float = 0.5):
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
        self._caption_groups: dict[str, list[str]] = {}
        self._caption_ts: dict[str, int] = {}

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

    @staticmethod
    def _format_retrieved(hits: list) -> str:
        """Format retrieved hits as caption + associated actions."""
        blocks = []
        for h in hits:
            actions = h.get("meta", {}).get("actions", [])
            if actions:
                action_lines = "\n".join(f"  - {a}" for a in actions)
                blocks.append(f"{h['text']}\n{action_lines}")
            else:
                blocks.append(h["text"])
        return "\n\n".join(blocks)

    def _sample(self, messages: list, stop: list) -> str:
        logger.info("[llm] prediction: generating")
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
        retrieved_text = self._format_retrieved(hits)

        # 2) Append retrieved context + prediction instruction to the existing message
        suffix_parts = []
        if retrieved_text:
            suffix_parts.append(
                f"\n\nHere is some relevant context about this user:\n"
                f"<context>\n{retrieved_text}\n</context>"
            )
        suffix_parts.append(
            f"\n\nPredict the next {future_len} actions the user will take. "
            f"Output ONLY <action>...</action> tags inside a larger <actions>...</actions> block, "
            f"with each action wrapped in its own <action> tag."
        )
        suffix = "".join(suffix_parts)

        msg = messages[0]
        content = msg["content"]
        if isinstance(content, list):
            for part in reversed(content):
                if isinstance(part, dict) and part.get("type") == "text":
                    part["text"] += suffix
                    break
        elif isinstance(content, str):
            msg["content"] = content + suffix

        actions_text = self._sample(messages, stop=["</actions>"])
        messages.append({"role": "assistant", "content": [
            {"type": "text", "text": actions_text}
        ]})

        cached_messages = [self._ensure_cache_control(m) for m in messages]

        result = {
            "retrieved": retrieved_text,
            "actions": actions_text,
            "messages": cached_messages,
            "timestamp": datetime.now().isoformat(),
            "model": self.model,
        }

        if self.predictions_file:
            with open(self.predictions_file, "a") as f:
                json.dump(result, f)
                f.write("\n")

        return result

    def index_context(self) -> None:
        """Index new context buffer events into the retriever (incremental).

        Events with a dense_caption are grouped by caption: the caption text
        becomes the retriever document and action texts accumulate in metadata.
        Re-adding the same caption triggers dedup, updating the existing doc
        with the growing actions list.  Events without a caption are indexed
        individually by their text.
        """
        if self.data_manager is None:
            return
        new_events = self.data_manager.buffer[self._indexed_context_count:]
        for event in new_events:
            text = event.get("text", "")
            dense_caption = event.get("dense_caption", "")
            if dense_caption:
                actions = self._caption_groups.setdefault(dense_caption, [])
                if text:
                    actions.append(text)
                ts = self._caption_ts.setdefault(dense_caption, int(event["timestamp"]))
                self.retriever.add(
                    dense_caption,
                    event_ts=ts,
                    namespace="context",
                    metadata={"actions": list(actions)},
                )
            elif text:
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

        past_actions_block = build_actions_block(past, include_descriptions=True)

        image_parts = []
        if num_imgs_per_sample is not None:
            for action in past[-num_imgs_per_sample:]:
                img_path = action.get("img_path")
                if img_path is not None:
                    buf = io.BytesIO()
                    Image.open(img_path).save(buf, format="PNG")
                    b64 = base64.b64encode(buf.getvalue()).decode()
                    image_parts.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    })

        task_desc = TASK_DESCRIPTION_WITH_IMAGES if image_parts else TASK_DESCRIPTION
        if image_parts:
            content = image_parts + [
                {"type": "text", "text": task_desc + "\n\n" + past_actions_block}
            ]
        else:
            content = [
                {"type": "text", "text": task_desc + "\n\n" + past_actions_block}
            ]

        messages = [{"role": "user", "content": content}]
        ts = past[0]["timestamp"]

        dense_caption = collect_dense_captions(past)
        return self.predict(messages, ts, future_len=future_len, past_actions=past_actions_block, dense_caption=dense_caption)

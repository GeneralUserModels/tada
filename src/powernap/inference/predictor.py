import asyncio
import copy
import json
import re
from datetime import datetime
from pathlib import Path

import tinker
from litellm import completion as litellm_completion

from powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION, TASK_DESCRIPTION_WITH_IMAGES, build_actions_block,
    build_think_user_message, build_revise_user_message, build_actions_user_message,
)
from powernap.longnap.retrievers import InMemoryBM25Temporal, jaccard_ngrams, mmr_select

VERIFIER_PROMPT_PATH = Path(__file__).resolve().parents[1] / "longnap" / "verifiers" / "accuracy.txt"


class Predictor:

    def __init__(self, renderer=None, tokenizer=None, max_tokens=512, temperature=1.0,
                 retriever=None, retriever_checkpoint=None, log_dir=None,
                 top_k=10, mmr_k=5, mmr_alpha=0.5, time_decay_lambda=0.5):
        self.renderer = renderer
        self.tokenizer = tokenizer
        self.model_path = None  # set by inference loop for logging
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
            self.predictions_file = log_path / "predictions.jsonl"


    def _sample(self, messages, stop, sampling_client):
        model_input = self.renderer.build_generation_prompt(messages)
        sample_result = asyncio.run(sampling_client.sample_async(
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

    def predict(self, messages, ts, future_len=4, past_actions="", sampling_client=None):
        """
        Run the 3-step Think → Revise → Actions flow.

        Args:
            messages: Initial conversation messages (user context).
                      The last message must be role=user with list content.
            ts: Timestamp for retrieval cutoff
            future_len: Number of actions to predict
            past_actions: Past actions block for retrieval query
            sampling_client: Tinker sampling client for this prediction
        """
        # 1) Think - merge think instruction into last user message, then sample
        #    Content is always a list (built by predict_from_snapshot), so just append a TextPart.
        messages = copy.deepcopy(messages)
        think_msg = build_think_user_message()
        messages[-1]["content"].append(
            {"type": "text", "text": "\n\n" + think_msg["content"]}
        )

        think_text = self._sample(messages, stop=["</rationale>"], sampling_client=sampling_client)
        messages.append({"role": "assistant", "content": think_text})

        # 2) Retrieve using think output
        query = think_text
        if past_actions:
            query = query + "\n\n" + past_actions

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
        revise_text = self._sample(messages, stop=["</revise>"], sampling_client=sampling_client)
        messages.append({"role": "assistant", "content": revise_text})

        # 4) Actions - add actions instruction and sample
        messages.append(build_actions_user_message(future_len))
        actions_text = self._sample(messages, stop=["</actions>"], sampling_client=sampling_client)

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

    def predict_from_snapshot(self, past, future_len, sampling_client=None,
                              num_imgs_per_sample=0):
        """Run prediction from a pre-sliced list of past actions."""
        past_actions_block = build_actions_block(past)

        # Always build content as a list so predict() can append TextParts directly
        if num_imgs_per_sample > 0:
            image_content = []
            for action in past[-num_imgs_per_sample:]:
                img = action.get("img")
                if img is not None:
                    image_content.append({"type": "image", "image": img.convert("RGB")})

            if image_content:
                content = image_content + [
                    {"type": "text", "text": TASK_DESCRIPTION_WITH_IMAGES + "\n\n" + past_actions_block}
                ]
            else:
                content = [{"type": "text", "text": TASK_DESCRIPTION + "\n\n" + past_actions_block}]
        else:
            content = [{"type": "text", "text": TASK_DESCRIPTION + "\n\n" + past_actions_block}]

        messages = [{
            "role": "user",
            "content": content,
        }]

        ts = datetime.strptime(past[0]["start_time"], "%Y-%m-%d_%H-%M-%S-%f").timestamp()

        return self.predict(messages, ts, future_len=future_len, past_actions=past_actions_block,
                            sampling_client=sampling_client)

    def score_prediction(self, predicted_actions, ground_truth_actions, reward_llm):
        if not re.search(r"<action>", predicted_actions):
            return 0.0

        verifier_prompt = VERIFIER_PROMPT_PATH.read_text()

        candidate_block = f"- **Candidate 1**:\n{predicted_actions}\n"
        prompt = verifier_prompt.format(
            ground_truth=ground_truth_actions,
            candidates=candidate_block,
        )

        response = litellm_completion(
            model=reward_llm,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.choices[0].message.content.strip()
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            text = match.group(1).strip()

        parsed = json.loads(text)
        return parsed["candidates"][0]["score"]

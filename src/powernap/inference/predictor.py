import json
import os
import re
from datetime import datetime
from pathlib import Path

from openai import OpenAI
from litellm import completion as litellm_completion

from powernap.longnap.trainer_utils import (
    TASK_DESCRIPTION, build_actions_block,
    build_think_user_message, build_revise_user_message, build_actions_user_message,
)
from powernap.longnap.retrievers import InMemoryBM25Temporal, jaccard_ngrams, mmr_select

VERIFIER_PROMPT_PATH = Path(__file__).resolve().parents[1] / "longnap" / "verifier.txt"


TINKER_OAI_URL = "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1"


class Predictor:

    def __init__(self, model_path=None, max_tokens=512, temperature=1.0,
                 retriever=None, retriever_checkpoint=None, log_dir=None,
                 top_k=10, mmr_k=10, mmr_alpha=0.5, time_decay_lambda=0.5):
        self.model_path = model_path
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_k = top_k
        self.mmr_k = mmr_k
        self.mmr_alpha = mmr_alpha
        self.time_decay_lambda = time_decay_lambda

        self.client = OpenAI(
            base_url=TINKER_OAI_URL,
            api_key=os.getenv("TINKER_API_KEY"),
        )

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


    def _sample(self, messages, stop, model_path=None):
        response = self.client.chat.completions.create(
            model=model_path or self.model_path,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            stop=stop,
        )
        return response.choices[0].message.content

    def predict(self, messages, ts, future_len=4, past_actions="", model_path_override=None):
        """
        Run the 3-step Think → Revise → Actions flow.

        Args:
            messages: Initial conversation messages (user context)
            ts: Timestamp for retrieval cutoff
            future_len: Number of actions to predict
            past_actions: Past actions block for retrieval query
            model_path_override: Freeze model path for thread-safe concurrent predictions
        """
        model_path = model_path_override or self.model_path

        # 1) Think - add think instruction and sample
        messages = messages + [build_think_user_message()]
        think_text = self._sample(messages, stop=["</think>"], model_path=model_path)
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
        revise_text = self._sample(messages, stop=["</revise>"], model_path=model_path)
        messages.append({"role": "assistant", "content": revise_text})

        # 4) Actions - add actions instruction and sample
        messages.append(build_actions_user_message(future_len))
        actions_text = self._sample(messages, stop=["</actions>"], model_path=model_path)


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

    def add_to_retriever(self, text, event_ts, namespace="train"):
        self.retriever.add(text, event_ts=event_ts, namespace=namespace)

    def predict_from_buffer(self, buffer, past_len, future_len, processor, model_path_override=None):
        """Build messages from buffer and run prediction."""
        past = buffer[-past_len:]

        past_actions_block = build_actions_block(past)

        messages = [{
            "role": "user",
            "content": TASK_DESCRIPTION + "\n\n" + past_actions_block,
        }]

        ts = datetime.strptime(past[0]["start_time"], "%Y-%m-%d_%H-%M-%S-%f").timestamp()

        return self.predict(messages, ts, future_len=future_len, past_actions=past_actions_block,
                            model_path_override=model_path_override)

    def score_prediction(self, predicted_actions, ground_truth_actions, reward_llm):
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

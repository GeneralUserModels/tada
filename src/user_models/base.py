import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

from litellm import completion as litellm_completion


class BasePredictor(ABC):

    _verifier_prompt_path: Path  # set by subclass __init__
    should_score_prediction: bool = False

    @abstractmethod
    def predict_from_snapshot(self, past: list, future_len: int, **kwargs) -> dict:
        """Run prediction from a pre-sliced list of past actions.

        Returns a dict with keys: think, retrieved, revise, actions, timestamp.
        """

    def score_prediction(
        self,
        predicted_actions: str,
        ground_truth_actions: str,
        reward_llm: str,
        api_key: str = None,
    ) -> float:
        if not re.search(r"<action>", predicted_actions):
            return 0.0

        verifier_prompt = self._verifier_prompt_path.read_text()
        candidate_block = f"- **Candidate 1**:\n{predicted_actions}\n"
        prompt = verifier_prompt.format(
            ground_truth=ground_truth_actions,
            candidates=candidate_block,
        )

        logger.info("[llm] reward scoring")
        response = litellm_completion(
            model=reward_llm,
            messages=[{"role": "user", "content": prompt}],
            api_key=api_key or None,
        )

        text = response.choices[0].message.content.strip()
        match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if match:
            text = match.group(1).strip()

        parsed = json.loads(text)
        return parsed["candidates"][0]["score"]

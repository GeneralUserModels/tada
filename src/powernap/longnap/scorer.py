"""
Reward scorer for LongNAP action predictions.

Extracts the scoring logic from the trainer into a reusable async scorer class.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import List, Optional

from litellm import completion as litellm_completion

logger = logging.getLogger(__name__)


@dataclass
class NormalizedCandidate:
    """Result of normalizing and validating a candidate action text."""
    text_for_judge: str
    is_valid: bool
    errors: List[str]
    penalty_score: float  # Range: 0 (perfect) to -0.5 (worst)


class RewardScorer:
    """
    Scores action predictions against ground truth using an LLM judge.
    
    This class encapsulates the reward computation logic used in LongNAP training.
    It can be used both synchronously (for batch scoring in the old trainer) and
    asynchronously (for the Env-based training loop).
    """
    
    def __init__(
        self,
        reward_llm: str = "gemini/gemini-3-flash-preview",
        api_key: str = "",
        accuracy_weight: float = 0.5,
        formatting_weight: float = 0.5,
        retry_on_failure: bool = True,
    ):
        """
        Initialize the reward scorer.

        Args:
            reward_llm: The LiteLLM model name for the reward model
            accuracy_weight: Weight for accuracy score in final reward (default: 0.5)
            formatting_weight: Weight for formatting score in final reward (default: 0.5)
            retry_on_failure: If True, retry LLM calls with sleep on failure (online).
                             If False, return 0.0 immediately on failure (offline).
        """
        self.reward_llm = reward_llm
        self.api_key = api_key or None
        self.retry_on_failure = retry_on_failure
        self.accuracy_weight = accuracy_weight
        self.formatting_weight = formatting_weight
        
        # Load verifier prompts
        verifiers_dir = os.path.join(os.path.dirname(__file__), "verifiers")
        
        accuracy_path = os.path.join(verifiers_dir, "accuracy.txt")
        with open(accuracy_path, "r") as f:
            self.accuracy_prompt_template = f.read()
        
        formatting_path = os.path.join(verifiers_dir, "formatting.txt")
        with open(formatting_path, "r") as f:
            self.formatting_prompt_template = f.read()
    
    # =========================================================================
    # Validation
    # =========================================================================
    
    def validate(self, action_text: Optional[str], expected_count: Optional[int] = None) -> NormalizedCandidate:
        """
        Validate an <actions> block. The input should already be just the
        <actions>...</actions> block — the same thing passed to the judge.
        
        Args:
            action_text: The <actions>...</actions> block from the model
            expected_count: Expected number of <action> tags (from ground truth).
                If provided, a penalty is applied when the count doesn't match.
            
        Returns:
            NormalizedCandidate with validation info and penalty
        """
        errors = []
        penalty = 0.0

        if not action_text:
            errors.append("Empty or None completion.")
            penalty -= 0.5
            return NormalizedCandidate(
                text_for_judge="",
                is_valid=False,
                errors=errors,
                penalty_score=penalty
            )

        if "<actions>" not in action_text or "</actions>" not in action_text:
            errors.append("Missing <actions> block.")
            penalty -= 0.5
            return NormalizedCandidate(
                text_for_judge=action_text,
                is_valid=False,
                errors=errors,
                penalty_score=penalty
            )

        # Validate action count
        if expected_count is not None:
            actual_count = len(re.findall(r"<action>.*?</action>", action_text, re.DOTALL))
            if actual_count != expected_count:
                errors.append(
                    f"Action count mismatch: expected {expected_count}, got {actual_count}."
                )
                return NormalizedCandidate(
                    text_for_judge=action_text,
                    is_valid=False,
                    errors=errors,
                    penalty_score=-0.5
                )

        return NormalizedCandidate(
            text_for_judge=action_text,
            is_valid=True,
            errors=errors,
            penalty_score=penalty
        )
    
    # =========================================================================
    # LLM Judge Scoring
    # =========================================================================
    
    def _build_candidates_block(self, candidate_texts: List[str]) -> str:
        """Build the markdown block passed to the verifier with all candidates."""
        out = []
        for j, c in enumerate(candidate_texts):
            out.append(f"- **Candidate {j + 1}**:\n{c}\n")
        return "".join(out)
    
    def _parse_accuracy_response(self, response_text: str, num_candidates: int) -> List[float]:
        """Parse the accuracy verifier response to extract scores."""
        scores = [0.0] * num_candidates
        if not response_text:
            logger.warning("Empty response from accuracy verifier")
            return scores

        text = response_text.strip()

        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1).strip()

        try:
            parsed = json.loads(text)
            candidates = parsed["candidates"]
            scores = [c["score"] for c in candidates]
            logger.info(f"Accuracy scores: {scores}")
            return scores
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse accuracy response: {e}. Returning default scores.")
            return scores
    
    def _parse_formatting_response(self, response_text: str) -> float:
        """Parse the formatting verifier response to extract score."""
        if not response_text:
            logger.warning("Empty response from formatting verifier")
            return 0.0

        text = response_text.strip()

        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1).strip()

        try:
            parsed = json.loads(text)
            score = parsed["score"]
            logger.info(f"Formatting score: {score}")
            return score
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse formatting response: {e}. Returning default score 0.0.")
            return 0.0
    
    def _call_llm_with_retry(self, prompt: str) -> str:
        """
        Call the LLM with retry logic.

        Args:
            prompt: The prompt to send to the LLM

        Returns:
            Response text from the LLM, or empty string on failure
        """
        while True:
            try:
                response = litellm_completion(
                    model=self.reward_llm,
                    messages=[{"role": "user", "content": prompt}],
                    api_key=self.api_key,
                )
                return response.choices[0].message.content
            except Exception as e:
                if self.retry_on_failure:
                    logger.warning(f"Reward LLM call failed: {e}. Retrying in 120s...")
                    time.sleep(120)
                else:
                    logger.warning(f"Reward LLM call failed: {e}. Returning empty response")
                    return ""
    
    @staticmethod
    def _zero_result() -> dict:
        return {"reward": 0.0, "accuracy": 0.0, "formatting": 0.0, "penalty": 0.0}

    def _call_judge_sync(self, action_text: str, ground_truth: str) -> dict:
        """
        Synchronously call both accuracy and formatting verifiers in parallel.

        Args:
            action_text: The predicted actions text
            ground_truth: The ground truth actions

        Returns:
            Dict with 'reward', 'accuracy', 'formatting', 'penalty' keys.
        """
        if not action_text or not re.search(r"<action>", action_text):
            return self._zero_result()

        # Validate the action text (count expected actions from ground truth)
        expected_count = len(re.findall(r"<action>.*?</action>", ground_truth, re.DOTALL))
        normalized = self.validate(action_text, expected_count=expected_count)
        
        if not normalized.is_valid:
            logger.warning(f"Validation failed: {normalized.errors}\nPrediction: {action_text}")
            return self._zero_result()
        
        # Build the prompts
        candidates_block = self._build_candidates_block([normalized.text_for_judge])
        
        # Accuracy prompt (needs ground truth)
        accuracy_prompt = self.accuracy_prompt_template.format(
            ground_truth=ground_truth,
            candidates=candidates_block
        )
        
        # Formatting prompt (only needs prediction)
        formatting_prompt = self.formatting_prompt_template.format(
            prediction=normalized.text_for_judge
        )
        
        # Call both verifiers in parallel using threads
        from concurrent.futures import ThreadPoolExecutor
        
        accuracy_score = 0.0
        formatting_score = 0.0
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_accuracy = executor.submit(self._call_llm_with_retry, accuracy_prompt)
            future_formatting = executor.submit(self._call_llm_with_retry, formatting_prompt)
            
            # Get accuracy result
            accuracy_response = future_accuracy.result()
            if accuracy_response:
                scores = self._parse_accuracy_response(accuracy_response, num_candidates=1)
                accuracy_score = scores[0] if scores else 0.0
            
            # Get formatting result
            formatting_response = future_formatting.result()
            if formatting_response:
                formatting_score = self._parse_formatting_response(formatting_response)
        
        # Combine scores with weights
        combined_score = (
            self.accuracy_weight * accuracy_score +
            self.formatting_weight * formatting_score
        )
        
        # Apply penalty from normalization
        penalty = normalized.penalty_score
        final_score = max(0.0, combined_score + penalty)
        
        logger.info(
            f"Scores - Accuracy: {accuracy_score:.3f}, Formatting: {formatting_score:.3f}, "
            f"Combined: {combined_score:.3f}, Penalty: {penalty:.3f}, "
            f"Final: {final_score:.3f}"
        )
        
        return {
            "reward": final_score,
            "accuracy": accuracy_score,
            "formatting": formatting_score,
            "penalty": penalty,
        }
    
    async def __call__(self, action_text: str, ground_truth: str) -> dict:
        """
        Async interface for scoring a single action prediction.
        
        This is the main interface used by LongNAPEnv.
        
        Args:
            action_text: The predicted actions text
            ground_truth: The ground truth actions
            
        Returns:
            Dict with 'reward', 'accuracy', 'formatting', 'penalty' keys.
        """
        # Run the sync call in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,  # Use default executor
            self._call_judge_sync,
            action_text,
            ground_truth
        )


def create_reward_scorer(
    reward_llm: str = "gemini/gemini-3-flash-preview",
    api_key: str = "",
    accuracy_weight: float = 0.5,
    formatting_weight: float = 0.5,
    retry_on_failure: bool = True,
) -> RewardScorer:
    """
    Factory function to create a reward scorer.

    Args:
        reward_llm: The LiteLLM model name for the reward model
        accuracy_weight: Weight for accuracy score in final reward (default: 0.5)
        formatting_weight: Weight for formatting score in final reward (default: 0.5)
        retry_on_failure: If True, retry LLM calls on failure (online).
                         If False, return 0.0 immediately (offline).

    Returns:
        A RewardScorer instance
    """
    return RewardScorer(
        reward_llm=reward_llm,
        api_key=api_key,
        accuracy_weight=accuracy_weight,
        formatting_weight=formatting_weight,
        retry_on_failure=retry_on_failure
    )

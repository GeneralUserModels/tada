"""
Reward scorer for LongNAP action predictions.

Extracts the scoring logic from the trainer into a reusable async scorer class.
"""

import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
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
        verifier_prompt_path: Optional[str] = None,
    ):
        """
        Initialize the reward scorer.
        
        Args:
            reward_llm: The LiteLLM model name for the reward model
            verifier_prompt_path: Path to the verifier prompt file. If None,
                                 uses the default verifier.txt in this directory.
        """
        self.reward_llm = reward_llm
        
        # Load verifier prompt
        if verifier_prompt_path is None:
            verifier_prompt_path = os.path.join(os.path.dirname(__file__), "verifier.txt")
        
        with open(verifier_prompt_path, "r") as f:
            self.verifier_prompt_template = f.read()
    
    # =========================================================================
    # Normalization and Validation
    # =========================================================================
    
    def _needs_normalization(self, text: str) -> bool:
        """Check if the text contains user/assistant blocks that need normalization."""
        return bool(re.search(r"^\s*(?:assistant|user)\b", text, re.MULTILINE))
    
    def _extract_actions_block(self, text: str) -> str:
        """Extract only the <actions>...</actions> block from the text."""
        match = re.search(r"<actions>(.*?)</actions>", text, re.DOTALL)
        if match:
            return f"<actions>{match.group(1)}</actions>"
        return text
    
    def normalize_and_validate(self, raw: Optional[str]) -> NormalizedCandidate:
        """
        Normalize by removing all 'user' blocks and keeping only 'assistant' blocks.
        Extract the <actions> block for the judge.
        Validate and apply penalties for missing or malformed blocks.
        
        Args:
            raw: The raw action text from the model
            
        Returns:
            NormalizedCandidate with the cleaned text and validation info
        """
        errors = []
        penalty = 0.0

        if not raw:
            errors.append("Empty or None completion.")
            penalty -= 0.5
            return NormalizedCandidate(
                text_for_judge="",
                is_valid=False,
                errors=errors,
                penalty_score=penalty
            )

        # Check if normalization is needed
        if not self._needs_normalization(raw):
            # No user/assistant blocks, just extract actions
            actions_text = self._extract_actions_block(raw)
            return NormalizedCandidate(
                text_for_judge=actions_text,
                is_valid=True,
                errors=[],
                penalty_score=0.0
            )

        # Ensure it starts with assistant block for parsing
        if not raw.strip().startswith("assistant"):
            raw = "assistant\n" + raw

        # Keep ONLY assistant blocks; remove user blocks
        assistant_blocks = re.findall(
            r"(?mis)^\s*assistant\s*(.*?)(?=^\s*(?:assistant|user)\b|\Z)",
            raw
        )

        if not assistant_blocks:
            errors.append("No assistant blocks found.")
            penalty -= 0.5
            return NormalizedCandidate(
                text_for_judge=raw.strip(),
                is_valid=False,
                errors=errors,
                penalty_score=penalty
            )

        # Join all assistant blocks
        full_text = "\n\n".join(block.strip() for block in assistant_blocks).strip()

        # Validate structure (optional - can be made stricter)
        if len(assistant_blocks) >= 1 and not assistant_blocks[0].strip().endswith("</think>"):
            errors.append("Missing or malformed </think> block.")
            penalty -= 0.15

        if len(assistant_blocks) >= 2 and not assistant_blocks[1].strip().endswith("</revise>"):
            errors.append("Missing or malformed </revise> block.")
            penalty -= 0.15

        # Extract the <actions> block for the judge
        actions_text = self._extract_actions_block(full_text)

        # Check if actions block exists
        if "<actions>" not in actions_text or "</actions>" not in actions_text:
            errors.append("Missing <actions> block.")
            penalty -= 0.2
            is_valid = False
        else:
            is_valid = len(errors) == 0

        # Clamp penalty to [-0.5, 0]
        penalty = max(-0.5, penalty)

        return NormalizedCandidate(
            text_for_judge=actions_text,
            is_valid=is_valid,
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
    
    def _parse_judge_response(self, response_text: str, num_candidates: int) -> List[float]:
        """Parse the judge LLM response to extract scores."""
        scores = [0.0] * num_candidates
        if not response_text:
            logger.warning("Empty response from judge LLM")
            return scores

        text = response_text.strip()

        # Extract JSON from markdown code blocks if present
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            text = json_match.group(1).strip()

        try:
            parsed = json.loads(text)
        except Exception as e:
            logger.warning(f"Failed to parse judge response: {e}")
            logger.warning(f"Response text: {text[:500]}")
            return scores

        if parsed is None:
            logger.warning(f"Could not parse judge response. Full response:\n{response_text[:1000]}")
            return scores

        try:
            candidates = parsed["candidates"]
            scores = [c["score"] for c in candidates]
            logger.info(f"Judge scores: {scores}")
        except (KeyError, TypeError) as e:
            logger.warning(f"Failed to extract scores from parsed response: {e}")
            logger.warning(f"Parsed object: {parsed}")

        return scores
    
    def _call_judge_sync(self, action_text: str, ground_truth: str) -> float:
        """
        Synchronously call the judge LLM to score a single action prediction.
        
        Args:
            action_text: The predicted actions text
            ground_truth: The ground truth actions
            
        Returns:
            Score between 0.0 and 1.0
        """
        # Normalize the action text
        normalized = self.normalize_and_validate(action_text)
        
        # Build the prompt
        candidates_block = self._build_candidates_block([normalized.text_for_judge])
        verifier_prompt = self.verifier_prompt_template.format(
            ground_truth=ground_truth,
            candidates=candidates_block
        )
        
        # Call the LLM
        try:
            response = litellm_completion(
                model=self.reward_llm,
                messages=[{"role": "user", "content": verifier_prompt}],
            )
            response_text = response.choices[0].message.content
            scores = self._parse_judge_response(response_text, num_candidates=1)
            score = scores[0] if scores else 0.0
        except Exception as e:
            logger.error(f"Error calling judge LLM: {e}")
            score = 0.0
        
        # Apply penalty from normalization
        final_score = max(0.0, score + normalized.penalty_score)
        return final_score
    
    async def __call__(self, action_text: str, ground_truth: str) -> float:
        """
        Async interface for scoring a single action prediction.
        
        This is the main interface used by LongNAPEnv.
        
        Args:
            action_text: The predicted actions text
            ground_truth: The ground truth actions
            
        Returns:
            Score between 0.0 and 1.0
        """
        # Run the sync call in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        score = await loop.run_in_executor(
            None,  # Use default executor
            self._call_judge_sync,
            action_text,
            ground_truth
        )
        return score
    
    # =========================================================================
    # Batch Scoring (for legacy trainer compatibility)
    # =========================================================================
    
    def score_batch_sync(
        self,
        actions_texts: List[List[str]],
        ground_truth_actions: List[str],
    ) -> List[List[float]]:
        """
        Score multiple groups of action predictions against their ground truths.
        
        This is used by the legacy trainer for batch scoring with ThreadPoolExecutor.
        
        Args:
            actions_texts: List of groups, where each group is a list of candidate texts
            ground_truth_actions: List of ground truth texts, one per group
            
        Returns:
            List of score lists, one per group
        """
        def process_single_group(action_group: List[str], solution: str) -> List[float]:
            # Normalize all candidates
            normalized_texts = [
                self.normalize_and_validate(a).text_for_judge
                for a in action_group
            ]
            
            # Build the prompt
            candidates_block = self._build_candidates_block(normalized_texts)
            verifier_prompt = self.verifier_prompt_template.format(
                ground_truth=solution,
                candidates=candidates_block
            )
            
            # Call the LLM
            try:
                response = litellm_completion(
                    model=self.reward_llm,
                    messages=[{"role": "user", "content": verifier_prompt}],
                )
                response_text = response.choices[0].message.content
                scores = self._parse_judge_response(response_text, len(action_group))
            except Exception as e:
                logger.error(f"Error calling judge LLM: {e}")
                scores = [0.0] * len(action_group)
            
            return scores
        
        # Process groups in parallel
        scores = [None] * len(actions_texts)
        with ThreadPoolExecutor() as executor:
            from concurrent.futures import as_completed
            
            future_map = {
                executor.submit(process_single_group, action_group, ground_truth_actions[idx]): idx
                for idx, action_group in enumerate(actions_texts)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    scores[idx] = future.result()
                except Exception as e:
                    logger.error(f"Error processing group {idx}: {e}")
                    scores[idx] = [0.0] * len(actions_texts[idx])
        
        return scores


def create_reward_scorer(reward_llm: str = "gemini/gemini-3-flash-preview") -> RewardScorer:
    """
    Factory function to create a reward scorer.
    
    Args:
        reward_llm: The LiteLLM model name for the reward model
        
    Returns:
        A RewardScorer instance
    """
    return RewardScorer(reward_llm=reward_llm)

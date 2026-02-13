"""
LongNAP Environment implementing the Env abstraction from tinker_cookbook.

This models the 3-step Think → Retrieve → Revise → Actions flow as an RL environment.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence

from tinker import ModelInput
from tinker_cookbook.completers import StopCondition
from tinker_cookbook.renderers import Renderer
from tinker_cookbook.rl.types import (
    Action,
    Env,
    EnvGroupBuilder,
    Metrics,
    RLDataset,
    StepResult,
    Trajectory,
)

from .retrievers import InMemoryBM25Temporal, mmr_select
from .trainer_utils import (
    build_think_user_message,
    build_revise_user_message,
    build_actions_user_message,
)

import copy

class LongNAPEnv(Env):
    """
    Environment for the LongNAP 3-step Think → Revise → Actions flow.
    
    Each episode consists of 3 steps:
    - Step 0 (Think): Model generates initial reasoning
    - Step 1 (Revise): Model gets retrieved context and revises reasoning
    - Step 2 (Actions): Model generates action predictions, gets reward
    
    The reward is only given at the final step, based on comparing
    predicted actions to ground truth.
    """
    
    # Phase constants
    PHASE_THINK = 0
    PHASE_REVISE = 1
    PHASE_ACTIONS = 2
    
    def __init__(
        self,
        input_data: Dict[str, Any],
        renderer: Renderer,
        tokenizer: Any,
        retriever: Optional[InMemoryBM25Temporal],
        reward_scorer: Callable,
        retrieval_top_k: int = 10,
        retrieval_mmr_k: int = 10,
        retrieval_mmr_alpha: float = 0.5,
        retrieval_time_decay_lambda: float = 0.5,
    ):
        """
        Initialize the LongNAP environment.
        
        Args:
            input_data: Dict containing 'messages', 'solution', 'ts', 'end_ts', 
                       'future_len', 'past_actions'
            renderer: Renderer for building model prompts
            tokenizer: Tokenizer for decoding actions
            retriever: BM25 retriever for context retrieval (optional)
            reward_scorer: Async callable(actions_text, ground_truth) -> float
            retrieval_top_k: Number of top results to retrieve
            retrieval_mmr_k: Number of results after MMR reranking
            retrieval_mmr_alpha: MMR diversity parameter
            retrieval_time_decay_lambda: Time decay for retrieval scores
        """
        self.input_data = input_data
        self.renderer = renderer
        self.tokenizer = tokenizer
        self.retriever = retriever
        self.reward_scorer = reward_scorer
        
        # Retrieval parameters
        self.retrieval_top_k = retrieval_top_k
        self.retrieval_mmr_k = retrieval_mmr_k
        self.retrieval_mmr_alpha = retrieval_mmr_alpha
        self.retrieval_time_decay_lambda = retrieval_time_decay_lambda
        
        # Extract data from input
        self.base_messages = input_data["messages"]
        self.ground_truth = input_data["solution"]
        self.ts = int(input_data.get("ts", 0))
        self.end_ts = int(input_data.get("end_ts", self.ts))
        self.future_len = input_data.get("future_len", 3)
        self.past_actions = input_data.get("past_actions", "")
        
        # State tracking
        self.phase = self.PHASE_THINK
        self.messages: List[Dict] = []
        self.think_text: str = ""
        self.revise_text: str = ""
        self.actions_text: str = ""
        
    @property
    def stop_condition(self) -> StopCondition:
        """Get stop condition based on current phase."""
        if self.phase == self.PHASE_THINK:
            return ["</rationale>"]
        elif self.phase == self.PHASE_REVISE:
            return ["</revise>"]
        else:  # PHASE_ACTIONS
            return ["</actions>"]
    
    def _decode(self, action: Action) -> str:
        """Decode action tokens to string."""
        return self.tokenizer.decode(action, skip_special_tokens=True)
    
    def _build_think_messages(self) -> List[Dict]:
        """
        Build the conversation for the Think phase.
        
        Properly merges the Think instruction with the base messages to preserve
        multimodal content (images) in the first user message.
        """
        messages = copy.deepcopy(self.base_messages)
        think_msg = build_think_user_message()
        
        # If there's already a user message, merge the think instruction into it
        # to avoid consecutive user messages (which some renderers don't handle well)
        if messages and messages[-1]["role"] == "user":
            last_content = messages[-1]["content"]
            think_content = think_msg["content"]
            
            if isinstance(last_content, str):
                # Text-only: simple concatenation
                messages[-1]["content"] = last_content + "\n\n" + think_content
            elif isinstance(last_content, list):
                # Multimodal: append text part
                messages[-1]["content"] = last_content + [
                    {"type": "text", "text": "\n\n" + think_content}
                ]
            else:
                # Fallback: just append
                messages.append(think_msg)
        else:
            messages.append(think_msg)
        
        return messages
    
    def _build_revise_messages(self, retrieved_text: str) -> List[Dict]:
        """Build the conversation for the Revise phase (after Think response)."""
        # At this point, messages ends with assistant's Think response
        # So we can safely add a new user message
        return self.messages + [build_revise_user_message(retrieved_text)]
    
    def _build_actions_messages(self) -> List[Dict]:
        """Build the conversation for the Actions phase (after Revise response)."""
        # At this point, messages ends with assistant's Revise response
        # So we can safely add a new user message
        return self.messages + [build_actions_user_message(self.future_len)]
    
    def _do_retrieval(self, query: str) -> str:
        """Query the retriever and return formatted context."""
        if self.retriever is None:
            return ""
        
        # Combine think output with past actions for better retrieval
        full_query = query
        if self.past_actions:
            full_query = query + "\n\n" + self.past_actions
        
        # Query retriever
        hits = self.retriever.query(
            full_query,
            k=self.retrieval_top_k,
            cutoff_ts=self.ts,
            namespaces=["train"],
            time_decay_lambda=self.retrieval_time_decay_lambda,
        )
        
        # Apply MMR for diversity
        if hits:
            items = [(h["text"], h["score"], h) for h in hits]
            selected = mmr_select(items, top_m=self.retrieval_mmr_k, alpha=self.retrieval_mmr_alpha)
            hits = [it[2] for it in selected]
        
        # Format retrieved texts
        return "\n\n".join(h["text"] for h in hits) if hits else ""
    
    async def initial_observation(self) -> tuple[ModelInput, StopCondition]:
        """Return the initial observation (Think prompt)."""
        self.messages = self._build_think_messages()
        prompt = self.renderer.build_generation_prompt(self.messages)
        return prompt, self.stop_condition
    
    async def step(self, action: Action) -> StepResult:
        """
        Process an action and return the next observation.
        
        Args:
            action: List of token IDs from the model's generation
            
        Returns:
            StepResult with next observation, reward, and done flag
        """
        action_text = self._decode(action)
        
        if self.phase == self.PHASE_THINK:
            # After Think: do retrieval, prepare Revise prompt
            self.think_text = action_text
            self.messages.append({"role": "assistant", "content": self.think_text})
            
            # Do retrieval
            retrieved_text = self._do_retrieval(self.think_text)
            
            # Build Revise prompt
            self.messages = self._build_revise_messages(retrieved_text)
            next_prompt = self.renderer.build_generation_prompt(self.messages)
            
            self.phase = self.PHASE_REVISE
            return StepResult(
                next_observation=next_prompt,
                next_stop_condition=self.stop_condition,
                reward=0.0,
                episode_done=False,
                logs={"phase": "think", "think_len": len(action)},
            )
        
        elif self.phase == self.PHASE_REVISE:
            # After Revise: prepare Actions prompt
            self.revise_text = action_text
            self.messages.append({"role": "assistant", "content": self.revise_text})
            
            # Build Actions prompt
            self.messages = self._build_actions_messages()
            next_prompt = self.renderer.build_generation_prompt(self.messages)
            
            self.phase = self.PHASE_ACTIONS
            return StepResult(
                next_observation=next_prompt,
                next_stop_condition=self.stop_condition,
                reward=0.0,
                episode_done=False,
                logs={"phase": "revise", "revise_len": len(action)},
            )
        
        else:  # PHASE_ACTIONS
            # After Actions: score and end episode
            self.actions_text = action_text
            self.messages.append({"role": "assistant", "content": self.actions_text})
            
            # Score the actions
            reward = await self.reward_scorer(self.actions_text, self.ground_truth)
            
            # Return final observation (not used, but required by interface)
            final_prompt = self.renderer.build_generation_prompt(self.messages)
            
            return StepResult(
                next_observation=final_prompt,
                next_stop_condition=self.stop_condition,
                reward=reward,
                episode_done=True,
                logs={
                    "phase": "actions",
                    "actions_len": len(action),
                    "reward": reward,
                },
            )


@dataclass(frozen=True)
class LongNAPEnvGroupBuilder(EnvGroupBuilder):
    """
    Builder for a group of LongNAP environments.
    
    Creates num_envs identical environments from the same input data.
    This enables GRPO-style per-group advantage normalization.
    """
    
    input_data: Dict[str, Any]
    renderer: Renderer
    tokenizer: Any
    retriever: Optional[InMemoryBM25Temporal]
    reward_scorer: Callable
    num_envs: int
    retrieval_top_k: int = 10
    retrieval_mmr_k: int = 10
    retrieval_mmr_alpha: float = 0.5
    retrieval_time_decay_lambda: float = 0.5
    
    async def make_envs(self) -> Sequence[Env]:
        """Create num_envs copies of the LongNAP environment."""
        return [
            LongNAPEnv(
                input_data=self.input_data,
                renderer=self.renderer,
                tokenizer=self.tokenizer,
                retriever=self.retriever,
                reward_scorer=self.reward_scorer,
                retrieval_top_k=self.retrieval_top_k,
                retrieval_mmr_k=self.retrieval_mmr_k,
                retrieval_mmr_alpha=self.retrieval_mmr_alpha,
                retrieval_time_decay_lambda=self.retrieval_time_decay_lambda,
            )
            for _ in range(self.num_envs)
        ]
    
    async def compute_group_rewards(
        self,
        trajectory_group: List[Trajectory],
        env_group: Sequence[Env]
    ) -> List[tuple[float, Metrics]]:
        """
        Compute group-level rewards and save retriever candidates for later ELBO-based selection.

        The per-step rewards are already computed in env.step(), so we return 0 here.
        Retriever winner selection is deferred to add_elbo_winner_to_retriever() which
        is called from the training step after ELBO logprob rewards are computed.
        """
        # Save retriever candidates (don't add yet — wait for ELBO rewards)
        if self.retriever is not None:
            candidates = []
            for env in env_group:
                if isinstance(env, LongNAPEnv) and env.revise_text:
                    past_actions = self.input_data.get("past_actions", "")
                    if past_actions:
                        text = past_actions.strip() + "\n\n<revise>\n" + env.revise_text.strip()
                    else:
                        text = "<revise>\n" + env.revise_text.strip()
                    candidates.append({"text": text, "ts": env.ts, "end_ts": env.end_ts})
                else:
                    candidates.append(None)
            object.__setattr__(self, '_retriever_candidates', candidates)

        # Return zero group reward (per-step rewards already computed)
        return [(0.0, {}) for _ in trajectory_group]

    def add_elbo_winner_to_retriever(self, rewards: list):
        """Add the trajectory with the highest ELBO reward to the retriever."""
        candidates = getattr(self, '_retriever_candidates', None)
        if not self.retriever or not candidates:
            return
        winner_idx = max(range(len(rewards)), key=lambda i: rewards[i])
        candidate = candidates[winner_idx]
        if candidate and candidate["text"].strip():
            self.retriever.add(
                text=candidate["text"],
                event_ts=candidate["ts"],
                visible_after_ts=candidate["ts"] + 1,
                namespace="train",
                metadata={"utility": rewards[winner_idx], "end_ts": candidate["end_ts"]},
            )

    def logging_tags(self) -> List[str]:
        """Return tags for logging aggregation."""
        return ["longnap"]

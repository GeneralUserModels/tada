import base64
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np
import tinker
from litellm import completion as litellm_completion
from torch.utils.data import Dataset
from tinker import types
from transformers import AutoTokenizer
from rich.console import Console
from rich.table import Table

from .retrievers import (
    InMemoryBM25Temporal,
    jaccard_ngrams,
    mmr_select,
)
from .trainer_utils import build_retrieve_prompt, build_revise_prompt, build_actions_prompt

# Optional wandb import
try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False



logger = logging.getLogger(__name__)


def print_prompt_completions_sample(
    prompts: List[str],
    completions: List[str],
    rewards: Dict[str, List[float]],
    advantages: List[float],
    step: int,
    num_to_print: int = 3,
):
    """Print a sample of prompts and completions using rich if available."""

    console = Console()
    table = Table(title=f"Step {step} - Sample Completions", show_lines=True)
    table.add_column("Prompt", style="cyan", max_width=50)
    table.add_column("Completion", style="green", max_width=60)
    table.add_column("Advantage", style="yellow")
    
    for reward_name in rewards.keys():
        table.add_column(reward_name, style="magenta")

    for i in range(min(num_to_print, len(prompts))):
        row = [
            prompts[i][:200] + "..." if len(prompts[i]) > 200 else prompts[i],
            completions[i][:300] + "..." if len(completions[i]) > 300 else completions[i],
            f"{advantages[i]:.4f}",
        ]
        for reward_name, reward_vals in rewards.items():
            if i < len(reward_vals):
                row.append(f"{reward_vals[i]:.4f}")
            else:
                row.append("N/A")
        table.add_row(*row)

    console.print(table)

@dataclass
class NormalizedCandidate:
    text_for_judge: str
    is_valid: bool
    errors: List[str]
    penalty_score: float  # Range: 0 (perfect) to -0.5 (worst)


class LongNAP():
    def __init__(
        self,
        model: str = "Qwen/Qwen3-VL-30B-A3B-Instruct",
        train_dataset: Dataset = None,
        eval_dataset: Dataset = None,
        reward_llm: str = "gemini-3-flash-preview",
        max_completion_length: int = 20,
        max_prompt_length: int = 100,
        num_generations: int = 16,
        temperature: float = 1.0,
        repetition_penalty: float = 0.0,
        shuffle_dataset: bool = False,
        num_iterations: int = 1,
        learning_rate: float = 1e-6,
        generation_batch_size: int = 16,
        log_completions: bool = False,
        wandb_log_unique_prompts: bool = False,
        num_completions_to_print: int = 10,
        retrieval_top_k: int = 10,
        retrieval_mmr_k: int = 10,
        retrieval_mmr_alpha: float = 0.5,
        retrieval_time_decay_lambda: float = 0.5,
        dedup_threshold: float = 0.8,
        log_every_n_steps: int = 10,
        log_dir: Optional[str] = None,
        log_to_wandb: bool = False,
        wandb_project: str = "napsack",
        wandb_run_name: str = "napsack",
        # Checkpointing parameters
        checkpoint_every_n_steps: int = 0,  # 0 = no checkpointing
        resume_from_checkpoint: Optional[str] = None,  # "auto", or a tinker:// path
    ):

        base_model = model
        self.service_client = tinker.ServiceClient()
        self.training_client = self.service_client.create_lora_training_client(
            base_model=base_model
        )
        self.tokenizer = self.training_client.get_tokenizer()
        self.reward_llm = reward_llm
        save_result = self.training_client.save_weights_for_sampler(name='napsack-model').result()
        self.latest_sampler_path = save_result.path
        self.sampling_client = self.service_client.create_sampling_client(model_path=self.latest_sampler_path)
        self.retrieval_params = types.SamplingParams(
            max_tokens=max_completion_length,
            temperature=temperature,
            stop=['</think>']) 
        self.revise_params = types.SamplingParams(
            max_tokens=max_completion_length,
            temperature=temperature,
            stop=["</revise>"]) 
        self.action_params = types.SamplingParams(
            max_tokens=max_completion_length,
            temperature=temperature,
            stop=["</actions>"]) 
        self.num_generations = num_generations
        self.learning_rate = learning_rate

        # Retrieval arguments
        self.retrieval_top_k = retrieval_top_k
        self.retrieval_mmr_k = retrieval_mmr_k
        self.retrieval_mmr_alpha = retrieval_mmr_alpha
        self.retrieval_time_decay_lambda = retrieval_time_decay_lambda

        # Training arguments
        self.max_prompt_length = max_prompt_length

        self._current_metric_prefix = None
        self.last_generations = {
            "prompts": [],
            "completions": [],
            "solution": [],
            "images": [],
        }
        self.last_generation_step = -1

        # Multi-step
        self._buffered_inputs = None

        # Initialize the metrics
        self._metrics = {"train": defaultdict(list), "eval": defaultdict(list)}
        self._total_train_tokens = 0
        self.log_completions = log_completions
        self.wandb_log_unique_prompts = wandb_log_unique_prompts
        self.num_completions_to_print = num_completions_to_print
        # Keep logs sized to the generation batch to record only outputs from the latest model update.
        self._logs = {
            "images": deque(maxlen=generation_batch_size),
            "prompt": deque(maxlen=generation_batch_size),
            "completion": deque(maxlen=generation_batch_size),
            "rewards": defaultdict(lambda: deque(maxlen=generation_batch_size)),
            "advantages": deque(maxlen=generation_batch_size),
        }


        # Retriever setup
        def dedup_fn(a, b): return jaccard_ngrams(a, b, n=3)
        self.retriever = InMemoryBM25Temporal(
            dedup_threshold=dedup_threshold,
            dedup_sim_fn=dedup_fn,
        )

        # Logging configuration
        self.log_completions = log_completions
        self.num_completions_to_print = num_completions_to_print
        self.log_to_wandb = log_to_wandb and WANDB_AVAILABLE
        self.log_every_n_steps = log_every_n_steps
        self.log_dir = log_dir
        self._step = 0
        self._start_time = None
        
        # Initialize wandb if requested
        if self.log_to_wandb:
            wandb.init(
                project=wandb_project,
                name=wandb_run_name,
                config={
                    "model": model,
                    "reward_llm": reward_llm,
                    "max_completion_length": max_completion_length,
                    "num_generations": num_generations,
                    "temperature": temperature,
                    "num_iterations": num_iterations,
                }
            )
        
        # Setup file logging if log_dir provided
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            self.metrics_file = os.path.join(log_dir, "metrics.jsonl")
            self.checkpoints_file = os.path.join(log_dir, "checkpoints.jsonl")
        else:
            self.metrics_file = None
            self.checkpoints_file = None

        # Checkpointing configuration
        self.checkpoint_every_n_steps = checkpoint_every_n_steps
        self._resume_step = 0  # Step to resume from (0 = start fresh)
        
        # Handle checkpoint resume
        if resume_from_checkpoint:
            self._resume_step = self._load_checkpoint(resume_from_checkpoint)

        # Completion logs buffer
        self._logs = {
            "images": deque(maxlen=num_generations * 8),
            "prompt": deque(maxlen=num_generations * 8),
            "completion": deque(maxlen=num_generations * 8),
            "rewards": defaultdict(lambda: deque(maxlen=num_generations * 8)),
            "advantages": deque(maxlen=num_generations * 8),
        }

    def generate_and_score_completions(
        self, 
        inputs: list[dict]
    ) -> dict:
        """
        Generate completions using Think→Retrieve→Revise→Actions flow.
        returns completions and mask        
        """

        B = len(inputs)
        prompts = [x["prompt"] for x in inputs]
        if "images" in inputs[0]:
            images = [example.get("images") for example in inputs]
        elif "image" in inputs[0]:
            images = [[example.get("image")] if example.get("image") is not None else None for example in inputs]
        else:
            images = None
        # Transformers requires at least one image in the batch, otherwise it throws an error
        if images is not None and all(img_list == [] for img_list in images):
            images = None

        # === Think→Retrieve→Revise→Actions ===
        B = len(prompts)

        kwargs_images = {"images": images} if images is not None else {}
        prompts_text = prompts  # Already formatted by dataset


        # Sample metadata per row (with fallback defaults)
        now_tss = [int(inputs[i].get("ts", self._step)) for i in range(B)]
        end_tss = [int(inputs[i].get("end_ts", now_tss[i])) for i in range(B)]
        future_lens = [int(inputs[i].get("future_len", 3)) for i in range(B)]
        sample_user_ids = [inputs[i].get("user_id", "default") for i in range(B)]
        tokenizer = self.training_client.get_tokenizer()
        
        
        # 1) THINK - Generate initial reasoning
        # Build think prompts using the utility function
        query_prompts = [build_retrieve_prompt(p) for p in prompts_text]
        query_prompt_tokens = [tokenizer.encode(p, **kwargs_images) for p in query_prompts]
        query_prompt_logprobs = [[0.0] * len(tokens) for tokens in query_prompt_tokens]

        
        query_futures = []
        for i in range(B):
            query_input = types.ModelInput.from_ints(tokens=query_prompt_tokens[i])
            future = self.sampling_client.sample(
                prompt=query_input,
                sampling_params=self.retrieval_params,
                num_samples=self.num_generations
            )
            query_futures.append(future)
        
        query_results = [f.result() for f in query_futures]
        query_tokens = [[r.tokens for r in result.sequences] for result in query_results]
        query_texts = [[self.tokenizer.decode(r.tokens) for r in result.sequences] for result in query_results]
        query_logprobs = [[r.logprobs for r in result.sequences] for result in query_results]
        # 2) RETRIEVE - Query retriever with think output
        retrieved_texts = []
        retr_queries = []
        for i in range(B):
            retr_queries.append([])
            for g in range(self.num_generations):
                query = query_texts[i][g]
                actions_str = inputs[i].get("actions", "")
                if actions_str:
                    query = query + "\n\n" + actions_str
                retr_queries[-1].append(query)

        # Query retriever
        # flatten the list of lists
        retr_queries = [item for sublist in retr_queries for item in sublist]
        # Expand cutoff timestamps to match flattened queries (B * num_generations)
        expanded_cutoffs = [ts for ts in now_tss for _ in range(self.num_generations)]
        hits_lists = [
            self.retriever.query(
                q,
                k=self.retrieval_top_k,
                cutoff_ts=int(cutoff),
                namespaces=["train"],
                time_decay_lambda=self.retrieval_time_decay_lambda,
            )
            for q, cutoff in zip(retr_queries, expanded_cutoffs)
        ]
        mmr_hits_lists = []
        for hits in hits_lists:
            if hits:
                items = [(h["text"], h["score"], h) for h in hits]
                selected = mmr_select(items, top_m=self.retrieval_mmr_k, alpha=self.retrieval_mmr_alpha)
                mmr_hits_lists.append([it[2] for it in selected])
            else:
                mmr_hits_lists.append([])

        retrieved_texts = ["\n\n".join(h["text"] for h in hits) for hits in mmr_hits_lists]

        # unflatten the list of lists
        retrieved_texts = [retrieved_texts[i:i+self.num_generations] for i in range(0, len(retrieved_texts), self.num_generations)]

        
        # 3) REVISE - Generate revised reasoning with retrieved context
        joint_revise = [[query_prompts[i] + query_texts[i][g] for g in range(self.num_generations)] for i in range(B)]
        revise_prompts = [[build_revise_prompt(joint_revise[i][g], retrieved_texts[i][g]) for g in range(self.num_generations)] for i in range(B)]
        revise_prompt_tokens = [[tokenizer.encode(p, **kwargs_images) for p in revise_prompts[i]] for i in range(B)]
        revise_prompt_logprobs = [[[0.0] * len(revise_prompt_tokens[i][g]) for g in range(self.num_generations)] for i in range(B)]
        revise_futures = []  # [B][num_generations]
        for i in range(B):
            gen_futures = []
            for g in range(self.num_generations):
                revise_input = types.ModelInput.from_ints(tokens=revise_prompt_tokens[i][g])
                future = self.sampling_client.sample(
                    prompt=revise_input,
                    sampling_params=self.revise_params,
                    num_samples=1
                )
                gen_futures.append(future)
            revise_futures.append(gen_futures)
        
        # Collect all results - revise_results is [B][num_generations], each with num_samples=1
        revise_results = [[f.result() for f in revise_futures[i]] for i in range(B)]
        revise_tokens = [[revise_results[i][g].sequences[0].tokens for g in range(self.num_generations)] for i in range(B)]
        revise_texts = [[self.tokenizer.decode(revise_tokens[i][g]) for g in range(self.num_generations)] for i in range(B)]
        revise_logprobs = [[revise_results[i][g].sequences[0].logprobs for g in range(self.num_generations)] for i in range(B)]
        # 4) ACTIONS - Generate action predictions
        actions_futures = []  # [B][num_generations]
        future_lens = [int(inputs[i].get("future_len", 3)) for i in range(B)]
        revise_blocks = [
            [
                build_revise_prompt(query_prompts[i] + query_texts[i][g], retrieved_texts[i][g]) + revise_texts[i][g]
                for g in range(self.num_generations)
            ]
            for i in range(B)
        ]
        actions_prompts = [
            [build_actions_prompt(revise_blocks[i][g], future_lens[i]) for g in range(self.num_generations)]
            for i in range(B)
        ]
        # TODO: check if kwargs_images is needed here
        actions_prompt_tokens = [[tokenizer.encode(p, **kwargs_images) for p in actions_prompts[i]] for i in range(B)]
        actions_prompt_logprobs = [[[0.0] * len(actions_prompt_tokens[i][g]) for g in range(self.num_generations)] for i in range(B)]
        
        for i in range(B):
            gen_futures = []
            for g in range(self.num_generations):
                actions_input = types.ModelInput.from_ints(tokens=actions_prompt_tokens[i][g])
                future = self.sampling_client.sample(
                    prompt=actions_input,
                    sampling_params=self.action_params,
                    num_samples=1
                )
                gen_futures.append(future)
            actions_futures.append(gen_futures)
        
        # Collect all results - actions_results is [B][num_generations], each with num_samples=1
        actions_results = [[f.result() for f in actions_futures[i]] for i in range(B)]
        actions_tokens = [[actions_results[i][g].sequences[0].tokens for g in range(self.num_generations)] for i in range(B)]
        actions_texts = [[self.tokenizer.decode(actions_tokens[i][g]) for g in range(self.num_generations)] for i in range(B)]
        actions_logprobs = [[actions_results[i][g].sequences[0].logprobs for g in range(self.num_generations)] for i in range(B)]

        ground_truth_actions = [inputs[i].get("solution", "") for i in range(B)]
        
        # build completion: retrieve prompt + query text + retrieved text + revise prompt + revise text + actions prompt + actions text
        # build mask: mask out non-model generated tokens
        completions, target_tokens, logprobs = [], [], []
        for i in range(B):
            for g in range(self.num_generations):
                completions.append(
                    query_prompt_tokens[i] + query_tokens[i][g] + \
                    revise_prompt_tokens[i][g] + revise_tokens[i][g] + \
                    actions_prompt_tokens[i][g] + actions_tokens[i][g])
                target_tokens.append(
                    [0] * len(query_prompt_tokens[i]) + query_tokens[i][g] + \
                    [0] * len(revise_prompt_tokens[i][g]) + revise_tokens[i][g] + \
                    [0] * len(actions_prompt_tokens[i][g]) + actions_tokens[i][g])
                logprobs.append(
                    query_prompt_logprobs[i] + query_logprobs[i][g] + \
                    revise_prompt_logprobs[i][g] + revise_logprobs[i][g] + \
                    actions_prompt_logprobs[i][g] + actions_logprobs[i][g])
        
        scores = self.score_completions(actions_texts, ground_truth_actions)
        
        # Return additional data needed for retriever updates
        return {
            "completions": completions,
            "target_tokens": target_tokens,
            "logprobs": logprobs,
            "scores": scores,
            "revise_texts": revise_texts,
            "now_tss": now_tss,
            "end_tss": end_tss,
        }

    ### Action text normalization and validation helper functions

    def _needs_normalization(self, text: str) -> bool:
        """
        Check if the text contains user/assistant blocks that need normalization.
        """
        return bool(re.search(r"^\s*(?:assistant|user)\b", text, re.MULTILINE))

    def _extract_actions_block(self, text: str) -> str:
        """
        Extract only the <actions>...</actions> block from the text.
        If not found, return the original text.
        """
        match = re.search(r"<actions>(.*?)</actions>", text, re.DOTALL)
        if match:
            return f"<actions>{match.group(1)}</actions>"
        return text

    def _normalize_and_validate_candidate(self, raw: Optional[str]):
        """
        Normalize by removing all 'user' blocks and keeping only 'assistant' blocks.
        Extract the <actions> block for the judge.
        Validate and apply penalties for missing or malformed blocks.
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

    def _build_candidates_block(self, c_texts: List[str]) -> str:
        """Build the markdown block passed to the verifier with all candidates."""
        out = []
        for j, c in enumerate(c_texts):
            out.append(f"- **Candidate {j + 1}**:\n{c}\n")
        return "".join(out)

    def _process_single_group(self, action_group, solution):
        verifier_path = os.path.join(os.path.dirname(__file__), "verifier.txt")
        with open(verifier_path, "r") as f:
            verifier_prompt = f.read()
        candidates_block = self._build_candidates_block(action_group)
        verifier_prompt = verifier_prompt.format(ground_truth=solution, candidates=candidates_block)
        response = litellm_completion(
            model=self.reward_llm,
            messages=[{"role": "user", "content": verifier_prompt}],
        )
        response_text = response.choices[0].message.content
        scores = self._parse_judge_response(response_text, len(action_group))
        return scores

    def score_completions(
        self,
        actions_texts,
        ground_truth_actions,
    ) -> dict:
        """
        Score completions using reward LLM with the judge prompt.
        """

        
        # normalize and validate the action texts
        normalized_actions_texts = []
        for action_text_group in actions_texts:
            for a in action_text_group:
                normalized = self._normalize_and_validate_candidate(a)
                normalized_actions_texts.append(normalized.text_for_judge)
        
        scores = [None] * len(actions_texts)
        with ThreadPoolExecutor() as executor:
            future_map = {
                executor.submit(self._process_single_group, action_text_group, ground_truth_actions): idx
                for idx, action_text_group in enumerate(actions_texts)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                scores[idx] = future.result()
        return scores


    def _parse_judge_response(self, response_text: str, num_candidates: int) -> list[float]:
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

        def _try_parse(raw: str) -> Optional[dict]:
            try:
                parsed = json.loads(raw)
            except Exception as e:
                logger.warning(f"Failed to parse judge response: {e}")
                logger.warning(f"Response text: {raw[:500]}")
                return None
            return parsed

        parsed = _try_parse(text)

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

    def _save_checkpoint(self, step: int) -> Optional[str]:
        """
        Save a checkpoint to Tinker (weights + optimizer state).
        
        Args:
            step: Current training step
            
        Returns:
            The tinker:// path to the saved checkpoint, or None if save failed
        """
        try:
            checkpoint_name = f"checkpoint_step_{step:06d}"
            save_result = self.training_client.save_state(name=checkpoint_name).result()
            checkpoint_path = save_result.path
            
            logger.info(f"Saved checkpoint at step {step}: {checkpoint_path}")
            
            # Record checkpoint in local file
            if self.checkpoints_file:
                checkpoint_info = {
                    "step": step,
                    "path": checkpoint_path,
                    "timestamp": time.time(),
                }
                with open(self.checkpoints_file, "a") as f:
                    f.write(json.dumps(checkpoint_info) + "\n")
            
            return checkpoint_path
        except Exception as e:
            logger.error(f"Failed to save checkpoint at step {step}: {e}")
            return None
    
    def _get_latest_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest checkpoint info from checkpoints.jsonl.
        
        Returns:
            Dict with 'step' and 'path' keys, or None if no checkpoints found
        """
        if not self.checkpoints_file or not os.path.exists(self.checkpoints_file):
            return None
        
        latest = None
        try:
            with open(self.checkpoints_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        checkpoint_info = json.loads(line)
                        if latest is None or checkpoint_info["step"] > latest["step"]:
                            latest = checkpoint_info
        except Exception as e:
            logger.error(f"Failed to read checkpoints file: {e}")
            return None
        
        return latest
    
    def _load_checkpoint(self, checkpoint_arg: str) -> int:
        """
        Load a checkpoint from Tinker.
        
        Args:
            checkpoint_arg: Either "auto" to load latest from checkpoints.jsonl,
                           or a specific tinker:// path
        
        Returns:
            The step number to resume from (0 if no checkpoint loaded)
        """
        checkpoint_path = None
        resume_step = 0
        
        if checkpoint_arg == "auto":
            # Auto-detect latest checkpoint from checkpoints.jsonl
            latest = self._get_latest_checkpoint()
            if latest:
                checkpoint_path = latest["path"]
                resume_step = latest["step"]
                logger.info(f"Auto-detected checkpoint at step {resume_step}: {checkpoint_path}")
            else:
                logger.info("No existing checkpoints found, starting fresh")
                return 0
        else:
            # Use the provided path directly
            checkpoint_path = checkpoint_arg
            # Try to extract step from path (e.g., "checkpoint_step_000100")
            match = re.search(r"checkpoint_step_(\d+)", checkpoint_path)
            if match:
                resume_step = int(match.group(1))
            else:
                # If we can't extract step, try to find it in checkpoints.jsonl
                if self.checkpoints_file and os.path.exists(self.checkpoints_file):
                    with open(self.checkpoints_file, "r") as f:
                        for line in f:
                            info = json.loads(line.strip())
                            if info.get("path") == checkpoint_path:
                                resume_step = info["step"]
                                break
        
        if checkpoint_path:
            try:
                logger.info(f"Loading checkpoint from {checkpoint_path}...")
                self.training_client.load_state(checkpoint_path).result()
                logger.info(f"Successfully loaded checkpoint, resuming from step {resume_step + 1}")
                return resume_step
            except Exception as e:
                logger.error(f"Failed to load checkpoint {checkpoint_path}: {e}")
                return 0
        
        return 0

    def train(self, data):
        """
        Main training loop.
        
        Args:
            data: Iterable of batches
        """
        self._metrics = {"train": defaultdict(list), "eval": defaultdict(list)}
        
        self._start_time = time.time()
        tokenizer = self.training_client.get_tokenizer()

        for step, batch in enumerate(data):
            # Skip steps that were already completed (when resuming)
            if step < self._resume_step:
                continue
            
            # Log if we're resuming
            if step == self._resume_step and self._resume_step > 0:
                logger.info(f"Resuming training from step {step}")
            
            self._step = step
            step_start_time = time.time()
            B = len(batch)
            # 1) Generate completions (Think → Retrieve → Revise → Actions)
            gen_result = self.generate_and_score_completions(batch)
            completions = gen_result["completions"]
            target_tokens = gen_result["target_tokens"]
            sampling_logprobs = gen_result["logprobs"]
            scores = gen_result["scores"]
            revise_texts = gen_result["revise_texts"]
            now_tss = gen_result["now_tss"]
            end_tss = gen_result["end_tss"]
            
            # 2) Flatten scores and compute advantages (per-group normalization like GRPO)
            flat_scores = []
            flat_advantages = []
            winner_indices = []  # Track which completions are winners (highest score per group)
            for group_idx, group_scores in enumerate(scores):
                group_scores = np.array(group_scores, dtype=np.float32)
                # Per-group advantage normalization
                group_mean = group_scores.mean()
                group_std = group_scores.std() + 1e-8
                group_advantages = (group_scores - group_mean) # / group_std
                flat_scores.extend(group_scores.tolist())
                flat_advantages.extend(group_advantages.tolist())
                # Track winner (highest score in group)
                winner_in_group = int(np.argmax(group_scores))
                winner_flat_idx = group_idx * self.num_generations + winner_in_group
                winner_indices.append((group_idx, winner_in_group, winner_flat_idx))
            
            # 2b) Add winning candidates to retriever
            self._add_winners_to_retriever(
                batch=batch,
                scores=scores,
                revise_texts=revise_texts,
                now_tss=now_tss,
                end_tss=end_tss,
                winner_indices=winner_indices,
                flat_scores=flat_scores,
            )
              
            # 3) Build Datum objects for Tinker's forward_backward
            data_list = []
            for i, (completion_tokens, mask_tokens, samp_lps, advantage) in enumerate(
                zip(completions, target_tokens, sampling_logprobs, flat_advantages)
            ):
                # mask_tokens has 0 for prompt positions, actual tokens for generated positions
                # Create weight mask: 1 for generated tokens (where mask != 0), 0 for prompt tokens
                weights = np.array([1.0 if t != 0 else 0.0 for t in mask_tokens], dtype=np.float32)

                # Per-token advantages (broadcast scalar advantage to sequence, masked by weights)
                per_token_advantages = advantage * weights

                # target_tokens should be actual token IDs (shifted by 1 for next-token prediction)
                # completion_tokens[1:] gives us the actual next tokens to predict
                datum = types.Datum(
                    model_input=types.ModelInput.from_ints(completion_tokens[:-1]),
                    loss_fn_inputs={
                        "target_tokens": np.array(completion_tokens[1:], dtype=np.int64),
                        "logprobs": np.array(samp_lps[1:], dtype=np.float32),
                        "advantages": per_token_advantages[1:],
                    }
                )
                data_list.append(datum)
    
            # 4) Forward-backward pass with importance sampling
            fwdbwd_future = self.training_client.forward_backward(
                data_list, 
                loss_fn="importance_sampling"
            )

            # 5) Optimizer step submit immediately for pipelining
            optim_future = self.training_client.optim_step(
                types.AdamParams(learning_rate=self.learning_rate)
            )

            # Wait for results
            fwdbwd_result = fwdbwd_future.result()
            optim_result = optim_future.result()
            
            # 6) Update sampling client with new weights for next iteration
            save_result = self.training_client.save_weights_for_sampler(name=f'napsack-model-step-{step}').result()
            self.latest_sampler_path = save_result.path
            self.sampling_client = self.service_client.create_sampling_client(model_path=self.latest_sampler_path)
            
            # 7) Accumulate metrics
            mean_reward = np.mean(flat_scores)
            std_reward = np.std(flat_scores)
            loss_value = fwdbwd_result.metrics.get("loss:sum", 0.0)
            
            self._metrics["train"]["loss"].append(loss_value)
            self._metrics["train"]["reward_mean"].append(mean_reward)
            self._metrics["train"]["reward_std"].append(std_reward)
            self._metrics["train"]["num_tokens"].append(sum(len(c) for c in completions))
            self._metrics["train"]["step_time"].append(time.time() - step_start_time)
            
            # 8) Update completion logs for display
            prompts_text = [batch[i // self.num_generations].get("prompt", "") for i in range(len(completions))]
            completions_text = [tokenizer.decode(c) for c in completions]
            self._update_logs(
                prompts=prompts_text[:self.num_completions_to_print],
                completions=completions_text[:self.num_completions_to_print],
                rewards={"score": flat_scores[:self.num_completions_to_print]},
                advantages=flat_advantages[:self.num_completions_to_print],
            )
            
            # 8) Log periodically
            if step % self.log_every_n_steps == 0:
                self.log(
                    logs={
                        "learning_rate": self.learning_rate,
                        "batch_size": B,
                        "num_generations": self.num_generations,
                    },
                    step=step,
                    start_time=step_start_time
                )
            
            # 9) Save checkpoint periodically (step+1 because we've completed this step)
            if self.checkpoint_every_n_steps > 0 and (step + 1) % self.checkpoint_every_n_steps == 0:
                self._save_checkpoint(step + 1)
        
        # Final logging
        if self.log_to_wandb:
            wandb.finish()
        
        # Save final checkpoint (only if not already saved at this step)
        if self.checkpoint_every_n_steps > 0:
            final_step = self._step + 1
            if final_step % self.checkpoint_every_n_steps != 0:
                self._save_checkpoint(final_step)

    def _add_winners_to_retriever(
        self,
        batch: List[Dict],
        scores: List[List[float]],
        revise_texts: List[List[str]],
        now_tss: List[int],
        end_tss: List[int],
        winner_indices: List[tuple],
        flat_scores: List[float],
    ) -> None:
        """
        Add winning candidates (highest score per group) to the retriever.
        
        Args:
            batch: Original batch of inputs
            scores: Scores per group [B][num_generations]
            revise_texts: Revise outputs [B][num_generations]
            now_tss: Current timestamps for each batch item
            end_tss: End timestamps for each batch item
            winner_indices: List of (group_idx, winner_in_group, flat_idx) tuples
            flat_scores: Flattened scores for logging
        """
        B = len(batch)
        
        for group_idx, winner_in_group, winner_flat_idx in winner_indices:
            # Get the winning revise text
            rev_txt = revise_texts[group_idx][winner_in_group] or ""
            
            # Get past actions from the input (if available)
            past_actions_txt = batch[group_idx].get("past_actions", "")
            past_actions_txt = batch[group_idx].get("actions", past_actions_txt)  # fallback to "actions" key
            
            # Combine past actions + revise trace (similar to old implementation)
            if past_actions_txt:
                combined_text = past_actions_txt.strip() + "\n\n<revise>\n" + rev_txt.strip()
            else:
                combined_text = "<revise>\n" + rev_txt.strip()
            
            # Skip if empty
            if not combined_text.strip():
                continue
            
            # Get the reward/utility for this winner
            utility = flat_scores[winner_flat_idx]
            
            # Get timestamps
            now_ts = now_tss[group_idx]
            end_ts = end_tss[group_idx]
            
            # Add to retriever with visible_delay=1 (visible after next timestep)
            self.retriever.add(
                text=combined_text,
                event_ts=now_ts,
                visible_after_ts=now_ts + 1,  # visible_delay=1
                namespace="train",
                metadata={
                    "utility": utility,
                    "end_ts": end_ts,
                    "step": self._step,
                },
            )
            
            logger.debug(f"Added to retriever: utility={utility:.4f}, ts={now_ts}")
        
        # Log retriever size
        logger.info(f"Retriever size: {self.retriever.N}")

    def log(
        self, 
        logs: Dict[str, float], 
        step: Optional[int] = None,
        start_time: Optional[float] = None
    ) -> None:
        """
        Log metrics to console, file, and wandb.
        
        Args:
            logs: Dictionary of metric names to values
            step: Current training step
            start_time: Start time for computing elapsed time
        """
        step = step if step is not None else self._step
        
        # Compute averages from accumulated metrics
        metrics = {}
        for mode in ["train", "eval"]:
            for key, val in self._metrics[mode].items():
                if len(val) > 0:
                    prefix = f"{mode}_" if mode == "eval" else ""
                    metrics[f"{prefix}{key}"] = sum(val) / len(val)
        
        # Merge with provided logs
        all_logs = {**logs, **metrics}
        all_logs["step"] = step
        
        # Add timing info
        if start_time is not None:
            all_logs["time_elapsed"] = time.time() - start_time
        elif self._start_time is not None:
            all_logs["time_elapsed"] = time.time() - self._start_time
        
        # Console logging
        self._log_to_console(all_logs, step)
        
        # File logging
        if self.metrics_file:
            self._log_to_file(all_logs)
        
        # Wandb logging
        if self.log_to_wandb and wandb.run is not None:
            self._log_to_wandb(all_logs, step)
        
        # Clear accumulated metrics
        for mode in ["train", "eval"]:
            self._metrics[mode].clear()
        
        # Log completions if enabled
        if self.log_completions and len(self._logs["prompt"]) > 0:
            self._log_completions(step)

    def _log_to_console(self, logs: Dict[str, float], step: int) -> None:
        """Print metrics to console."""
            
        console = Console()
        table = Table(title=f"Step {step}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        
        for key, val in sorted(logs.items()):
            if isinstance(val, float):
                table.add_row(key, f"{val:.6f}")
            else:
                table.add_row(key, str(val))
        
        console.print(table)

    def _log_to_file(self, logs: Dict[str, Any]) -> None:
        """Append metrics to JSONL file."""
        with open(self.metrics_file, "a") as f:
            f.write(json.dumps(logs) + "\n")

    def _log_to_wandb(self, logs: Dict[str, Any], step: int) -> None:
        """Log metrics to wandb."""
        wandb.log(logs, step=step)

    def _log_completions(self, step: int) -> None:
        """Log sample completions to console and wandb."""
        # Console logging
        if self.log_completions:
            print_prompt_completions_sample(
                list(self._logs["prompt"]),
                list(self._logs["completion"]),
                {k: list(v) for k, v in self._logs["rewards"].items()},
                list(self._logs["advantages"]),
                step,
                self.num_completions_to_print,
            )
        
        # Wandb table logging
        if self.log_to_wandb and wandb.run is not None:
            import pandas as pd
            
            table_data = {
                "step": [str(step)] * len(self._logs["prompt"]),
                "prompt": list(self._logs["prompt"]),
                "completion": list(self._logs["completion"]),
                "advantage": list(self._logs["advantages"]),
            }
            
            for reward_name, reward_vals in self._logs["rewards"].items():
                table_data[reward_name] = list(reward_vals)
            
            df = pd.DataFrame(table_data)
            wandb.log({"completions": wandb.Table(dataframe=df)}, step=step)
        
        # Clear completion logs
        self._logs["prompt"].clear()
        self._logs["completion"].clear()
        self._logs["advantages"].clear()
        for key in self._logs["rewards"]:
            self._logs["rewards"][key].clear()

    def _update_logs(
        self, 
        prompts: List[str], 
        completions: List[str], 
        rewards: Dict[str, List[float]], 
        advantages: List[float],
        images: Optional[List[Any]] = None
    ) -> None:
        """Update the completion logs buffer."""
        self._logs["prompt"].extend(prompts)
        self._logs["completion"].extend(completions)
        self._logs["advantages"].extend(advantages)
        
        for reward_name, reward_vals in rewards.items():
            self._logs["rewards"][reward_name].extend(reward_vals)
        
        if images:
            self._logs["images"].extend(images)
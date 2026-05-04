"""Pydantic schemas used for moments structured LLM outputs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CandidatePayload(StrictModel):
    id: str
    slug: str
    topic: str
    title: str
    description: str
    cadence: Literal["once", "scheduled", "trigger"]
    schedule: str = Field(
        min_length=1,
        description="Use the actual schedule for scheduled cadence; use not_applicable for once or trigger cadence.",
    )
    trigger: str = Field(
        min_length=1,
        description="Use the actual trigger condition for trigger cadence; use not_applicable for once or scheduled cadence.",
    )
    confidence: float
    usefulness: int
    specific_instructions: str
    desired_artifact: str
    evidence: list[str]
    source_paths: list[str]
    why_now: str
    user_value: str


class MomentIdea(StrictModel):
    title: str
    topic_hint: str
    artifact: str
    why_useful: str
    evidence: list[str]
    source_paths: list[str]
    cadence_hint: Literal["once", "scheduled", "trigger"]
    relation_to_existing: Literal["new", "possible_update", "duplicate", "weak"]


class IdeaPayload(StrictModel):
    ideas: list[MomentIdea] = []
    notes: str = ""


class DraftRejectOp(StrictModel):
    id: str
    reason: str


class DraftRemoveOp(StrictModel):
    id: str
    reason: str


class DraftActionPayload(StrictModel):
    upserts: list[CandidatePayload] = []
    rejected: list[DraftRejectOp] = []
    remove: list[DraftRemoveOp] = []
    notes: str = ""


class ReconcileUpdate(StrictModel):
    candidate_id: str
    accepted_slug: str
    reason: str


class ReconcilePayload(StrictModel):
    candidates: list[CandidatePayload]
    updates: list[ReconcileUpdate] = []
    rejected: list[DraftRejectOp] = []
    notes: str = ""


class PromotionReject(StrictModel):
    id: str
    reason: str


class PromotionPayload(StrictModel):
    promoted: list[str]
    rejected: list[PromotionReject] = []

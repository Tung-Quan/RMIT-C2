"""Pydantic models for the standalone Qwen reranker API."""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str
    gpu: str | None = None


class ParserHealthResponse(BaseModel):
    configured: bool
    loaded: bool
    device: str
    model: str


class ModelInfoResponse(BaseModel):
    model_name: str
    model_version: str
    model_path: str
    device: str
    score_type: str
    score_temperature: float
    max_text_chars: int
    max_pairs: int
    max_candidates: int
    batch_pair_size: int
    batch_max_total_pairs: int


class RerankPair(BaseModel):
    pair_id: str
    query: str
    document: str


class RerankRequest(BaseModel):
    pairs: List[RerankPair]


class ScoreResult(BaseModel):
    raw_score: float
    sigmoid_score: float
    calibrated_score: float
    display_score: int


class RerankResult(ScoreResult):
    pair_id: str


class RerankResponse(BaseModel):
    model_name: str
    model_version: str
    device: str
    results: List[RerankResult]


class CVJobGroupScoreRequest(BaseModel):
    job_text: str
    cv_groups: Dict[str, str]


class CVJobGroupScoreResponse(BaseModel):
    model_name: str
    model_version: str
    device: str
    overall: ScoreResult
    group_scores: Dict[str, ScoreResult]
    final_score: int
    label: str
    best_groups: List[str]
    weak_groups: List[str]
    notes: List[str]


class BatchCandidateRequest(BaseModel):
    candidate_id: str
    candidate_name: str | None = None
    cv_groups: Dict[str, str]


class BatchGroupScoreRequest(BaseModel):
    job_text: str
    candidates: List[BatchCandidateRequest]


class RankedCandidateResponse(BaseModel):
    rank: int
    candidate_id: str
    candidate_name: str | None = None
    overall: ScoreResult
    group_scores: Dict[str, ScoreResult]
    final_score: int
    label: str
    best_groups: List[str]
    weak_groups: List[str]
    ranking_raw_score: float
    notes: List[str]


class BatchGroupScoreResponse(BaseModel):
    model_name: str
    model_version: str
    device: str
    candidate_count: int
    pair_count: int
    batch_pair_size: int
    elapsed_ms: int
    ranked_candidates: List[RankedCandidateResponse]

from typing import Literal
from ai_service.job_schemas import ParsedJobProfile
from ai_service.cv_schemas import CandidateProfile

class CriterionMatchResult(BaseModel):
    criterion_index: int
    criterion_name: str
    criterion_source_text: str | None = None
    importance: Literal["required", "preferred"]
    status: Literal["matched", "not_matched"]
    explanation: str
    evidence_text: str | None = None
    evidence_name: str | None = None
    internal_evidence_score: float | None = None

class CandidateMatchResult(BaseModel):
    application_id: int
    criterion_results: List[CriterionMatchResult]

class MatchApplicationRequest(BaseModel):
    application_id: int
    cv_parse_revision: int
    candidate_profile: CandidateProfile

class MatchApplicationsRequest(BaseModel):
    job_profile: ParsedJobProfile
    applications: List[MatchApplicationRequest]

class MatchApplicationsResponse(BaseModel):
    model_name: str
    results: List[CandidateMatchResult]

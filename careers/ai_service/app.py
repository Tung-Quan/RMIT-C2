"""FastAPI app for the standalone Qwen3-Reranker AI service."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, List, Sequence

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import JSONResponse

from ai_service.job_parser import JobParserError, parse_job
from ai_service.job_schemas import ParsedJobProfile, RawJobCreate
from ai_service.llm.qwen_client import (
    ModelGenerationError,
    ModelLoadError,
    QwenGenerativeClient,
)
from ai_service.qwen_reranker import MODEL_NAME, MODEL_VERSION, QwenReranker
from ai_service.schemas import (
    BatchGroupScoreRequest,
    BatchGroupScoreResponse,
    CVJobGroupScoreRequest,
    CVJobGroupScoreResponse,
    HealthResponse,
    ModelInfoResponse,
    ParserHealthResponse,
    RankedCandidateResponse,
    RerankRequest,
    RerankResponse,
    ScoreResult,
    MatchApplicationsRequest,
    MatchApplicationsResponse,
    CandidateMatchResult,
    CriterionMatchResult,
)
from ai_service.scoring import (
    aggregate_group_scores,
    calibrate_raw_score,
    join_cv_groups,
    truncate_pairs,
)


load_dotenv(Path(__file__).with_name(".env"))
load_dotenv()


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


MAX_TEXT_CHARS = _env_int("QWEN_MAX_TEXT_CHARS", 12000)
MAX_PAIRS = _env_int("QWEN_MAX_PAIRS", 128)
SCORE_TEMPERATURE = _env_float("QWEN_SCORE_TEMPERATURE", 3.0)
MAX_CANDIDATES = _env_int("QWEN_MAX_CANDIDATES", 50)
BATCH_PAIR_SIZE = _env_int("QWEN_BATCH_PAIR_SIZE", 32)
BATCH_MAX_TOTAL_PAIRS = _env_int("QWEN_BATCH_MAX_TOTAL_PAIRS", 512)
RERANKER_MATCH_THRESHOLD = _env_float("RERANKER_MATCH_THRESHOLD", 0.65)
AI_SERVICE_API_KEY = os.getenv("AI_SERVICE_API_KEY", "").strip()

FIT_NOTES = [
    "This score is a semantic relevance estimate, not an automatic hiring decision.",
    "Raw scores should be preferred for ranking candidates within the same job.",
]

logger = logging.getLogger("ai_service.app")

reranker = QwenReranker()
parser_client = QwenGenerativeClient()

# Protect the generative model from concurrent execution to avoid GPU OOM.
PARSER_MAX_CONCURRENCY = _env_int("JOB_PARSER_MAX_CONCURRENCY", 1)
parser_semaphore = asyncio.Semaphore(PARSER_MAX_CONCURRENCY)
JOB_PARSER_PRELOAD = os.getenv("JOB_PARSER_PRELOAD", "false").strip().lower() == "true"


def require_api_key(
    x_ai_service_key: str | None = Header(default=None, alias="X-AI-Service-Key"),
) -> None:
    if not AI_SERVICE_API_KEY:
        return
    if x_ai_service_key != AI_SERVICE_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing AI service API key",
        )


@asynccontextmanager
async def lifespan(_: FastAPI):
    reranker.load()
    if JOB_PARSER_PRELOAD:
        logger.info("Preloading parser model as requested by JOB_PARSER_PRELOAD")
        try:
            # We run it in a thread so it doesn't block the loop startup.
            await asyncio.to_thread(parser_client.load)
        except Exception as exc:
            logger.error(f"Failed to preload parser: {exc}")
    yield


app = FastAPI(
    title="Qwen3 AI Service",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        model_loaded=reranker.model_loaded,
        device=reranker.device,
        gpu=reranker.gpu_name,
    )


@app.get("/health/parser", response_model=ParserHealthResponse)
def health_parser() -> ParserHealthResponse:
    return ParserHealthResponse(
        configured=True,
        loaded=parser_client.is_loaded,
        device=parser_client._device_setting,
        model=os.path.basename(parser_client.model_path),
    )


@app.post("/parse-job", response_model=ParsedJobProfile)
async def parse_job_endpoint(
    request: RawJobCreate, _: None = Depends(require_api_key)
) -> ParsedJobProfile:
    # 1. Validation and preparation
    try:
        job_input = request.to_parsing_input()
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_input", "message": str(exc)},
        )

    # 2. Concurrency check and generation
    t0 = time.perf_counter()
    async with parser_semaphore:
        wait_time = time.perf_counter() - t0
        if wait_time > 1.0:
            logger.info(f"Parser slot wait time: {wait_time:.2f}s")

        t_gen_start = time.perf_counter()

        # Track if it retries internally by wrapping the client
        class _CountingClient:
            def __init__(self, inner):
                self._inner = inner
                self.calls = 0

            def generate(self, prompt: str) -> str:
                self.calls += 1
                return self._inner.generate(prompt)

        counting_client = _CountingClient(parser_client)

        try:
            # parse_job is fully synchronous and blocks. Must run in thread.
            profile = await asyncio.to_thread(parse_job, job_input, counting_client)
        except JobParserError as exc:
            logger.error(f"Job parser domain error: {exc}")
            raise HTTPException(
                status_code=500,
                detail={"error": "job_parser_failed", "message": str(exc)},
            )
        except ModelLoadError as exc:
            logger.error(f"Parser model load error: {exc}")
            raise HTTPException(
                status_code=503,
                detail={"error": "job_parser_unavailable", "message": "The job parser is temporarily unavailable."},
            )
        except ModelGenerationError as exc:
            logger.error(f"Parser model generation error: {exc}")
            raise HTTPException(
                status_code=502,
                detail={"error": "job_parser_generation_failed", "message": "The job parser failed to generate output."},
            )
        except Exception as exc:
            logger.error(f"Unexpected error during parsing: {exc}")
            raise HTTPException(
                status_code=500,
                detail={"error": "internal_error", "message": "An unexpected error occurred."},
            )

        gen_time = time.perf_counter() - t_gen_start
        logger.info(
            f"Parsed job '{profile.normalized_title}': "
            f"{len(profile.criteria)} criteria, "
            f"calls={counting_client.calls}, "
            f"gen_time={gen_time:.1f}s"
        )
        return profile


from ai_service.cv_parser import parse_cv
from ai_service.cv_schemas import CandidateProfile, CVParsingInput
from ai_service.cv_cleaning import clean_cv_text

@app.post("/parse-cv", response_model=CandidateProfile)
async def parse_cv_endpoint(
    request: CVParsingInput, _: None = Depends(require_api_key)
) -> CandidateProfile:
    # 1. Validation and preparation
    try:
        cleaned_text = clean_cv_text(request.document_text)
        if not cleaned_text:
            raise ValueError("CV text is empty after cleaning.")
        cv_input = CVParsingInput(document_text=cleaned_text)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_input", "message": str(exc)},
        )

    # 2. Concurrency check and generation
    t0 = time.perf_counter()
    async with parser_semaphore:
        wait_time = time.perf_counter() - t0
        if wait_time > 1.0:
            logger.info(f"CV Parser slot wait time: {wait_time:.2f}s")

        t_gen_start = time.perf_counter()

        class _CountingClient:
            def __init__(self, inner):
                self._inner = inner
                self.calls = 0

            def generate(self, prompt: str) -> str:
                self.calls += 1
                return self._inner.generate(prompt)

        counting_client = _CountingClient(parser_client)

        try:
            profile = await asyncio.to_thread(parse_cv, cv_input, counting_client)
        except JobParserError as exc:
            logger.error(f"CV parser domain error: {exc}")
            raise HTTPException(
                status_code=500,
                detail={"error": "cv_parser_failed", "message": str(exc)},
            )
        except ModelLoadError as exc:
            logger.error(f"Parser model load error: {exc}")
            raise HTTPException(
                status_code=503,
                detail={"error": "job_parser_unavailable", "message": "The parser is temporarily unavailable."},
            )
        except ModelGenerationError as exc:
            logger.error(f"Parser model generation error: {exc}")
            raise HTTPException(
                status_code=502,
                detail={"error": "job_parser_generation_failed", "message": "The parser failed to generate output."},
            )
        except Exception as exc:
            logger.error(f"Unexpected error during parsing: {exc}")
            raise HTTPException(
                status_code=500,
                detail={"error": "internal_error", "message": "An unexpected error occurred."},
            )

        gen_time = time.perf_counter() - t_gen_start
        logger.info(
            f"Parsed CV: {len(profile.evidence_items)} evidence items, "
            f"calls={counting_client.calls}, "
            f"gen_time={gen_time:.1f}s"
        )
        return profile



@app.get("/model-info", response_model=ModelInfoResponse)
def model_info(_: None = Depends(require_api_key)) -> ModelInfoResponse:
    return ModelInfoResponse(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        model_path=reranker.model_path,
        device=reranker.device,
        score_type="raw_logit_sigmoid_and_calibrated",
        score_temperature=SCORE_TEMPERATURE,
        max_text_chars=MAX_TEXT_CHARS,
        max_pairs=MAX_PAIRS,
        max_candidates=MAX_CANDIDATES,
        batch_pair_size=BATCH_PAIR_SIZE,
        batch_max_total_pairs=BATCH_MAX_TOTAL_PAIRS,
    )


@app.post("/rerank", response_model=RerankResponse)
def rerank(request: RerankRequest, _: None = Depends(require_api_key)) -> RerankResponse:
    _validate_rerank_request(request)

    pair_ids = [pair.pair_id.strip() for pair in request.pairs]
    model_pairs = truncate_pairs(
        [(pair.query.strip(), pair.document.strip()) for pair in request.pairs],
        MAX_TEXT_CHARS,
    )

    raw_scores, sigmoid_scores = _predict_model_pairs(model_pairs)

    results = []
    for pair_id, raw_score, sigmoid_score in zip(pair_ids, raw_scores, sigmoid_scores):
        calibrated = calibrate_raw_score(raw_score, SCORE_TEMPERATURE)
        calibrated["sigmoid_score"] = float(sigmoid_score)
        results.append({"pair_id": pair_id, **calibrated})

    return RerankResponse(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        device=reranker.device,
        results=results,
    )


@app.post("/cv-job/group-score", response_model=CVJobGroupScoreResponse)
def cv_job_group_score(
    request: CVJobGroupScoreRequest,
    _: None = Depends(require_api_key),
) -> CVJobGroupScoreResponse:
    job_text = request.job_text.strip()
    cv_groups = _clean_cv_groups(request.cv_groups)

    if not job_text:
        raise HTTPException(status_code=400, detail="job_text must not be empty")
    if not cv_groups:
        raise HTTPException(status_code=400, detail="cv_groups must contain at least one non-empty group")

    full_cv = join_cv_groups(cv_groups)
    ordered_pairs: List[tuple[str, str, str]] = [("overall", job_text, full_cv)]
    ordered_pairs.extend(
        (
            group_name,
            job_text,
            f"[CV GROUP: {group_name.upper()}]\n{group_text}",
        )
        for group_name, group_text in cv_groups.items()
    )

    if len(ordered_pairs) > MAX_PAIRS:
        raise HTTPException(status_code=400, detail=f"Too many groups. Maximum pairs per request is {MAX_PAIRS}")

    model_pairs = truncate_pairs(
        [(query, document) for _, query, document in ordered_pairs],
        MAX_TEXT_CHARS,
    )

    scores = _score_model_pairs(model_pairs)
    scored = {
        pair_id: score
        for (pair_id, _, _), score in zip(ordered_pairs, scores)
    }

    overall = scored["overall"]
    group_scores = {group_name: score for group_name, score in scored.items() if group_name != "overall"}
    aggregate = aggregate_group_scores(
        _score_to_dict(overall),
        {group_name: _score_to_dict(score) for group_name, score in group_scores.items()},
    )

    return CVJobGroupScoreResponse(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        device=reranker.device,
        overall=overall,
        group_scores=group_scores,
        final_score=aggregate["final_score"],
        label=aggregate["label"],
        best_groups=aggregate["best_groups"],
        weak_groups=aggregate["weak_groups"],
        notes=FIT_NOTES,
    )


@app.post("/cv-job/batch-group-score", response_model=BatchGroupScoreResponse)
def cv_job_batch_group_score(
    request: BatchGroupScoreRequest,
    _: None = Depends(require_api_key),
) -> BatchGroupScoreResponse:
    started_at = time.perf_counter()
    job_text = request.job_text.strip()
    if not job_text:
        raise HTTPException(status_code=400, detail="job_text must not be empty")
    if not request.candidates:
        raise HTTPException(status_code=400, detail="candidates must not be empty")
    if len(request.candidates) > MAX_CANDIDATES:
        raise HTTPException(status_code=400, detail=f"Too many candidates. Maximum is {MAX_CANDIDATES}")

    candidate_records = []
    flat_pairs: List[tuple[str, str]] = []
    for index, candidate in enumerate(request.candidates):
        candidate_id = candidate.candidate_id.strip()
        if not candidate_id:
            raise HTTPException(status_code=400, detail=f"candidates[{index}].candidate_id must not be empty")
        if not candidate.cv_groups:
            raise HTTPException(status_code=400, detail=f"candidates[{index}].cv_groups must not be empty")

        cv_groups = _clean_cv_groups(candidate.cv_groups)
        if not cv_groups:
            raise HTTPException(
                status_code=400,
                detail=f"candidates[{index}].cv_groups must contain at least one non-empty group",
            )

        candidate_pair_ids = ["overall", *cv_groups.keys()]
        candidate_records.append(
            {
                "candidate_id": candidate_id,
                "candidate_name": candidate.candidate_name,
                "pair_ids": candidate_pair_ids,
            }
        )

        full_cv = join_cv_groups(cv_groups)
        flat_pairs.append((job_text, full_cv))
        flat_pairs.extend(
            (job_text, f"[CV GROUP: {group_name.upper()}]\n{group_text}")
            for group_name, group_text in cv_groups.items()
        )

    pair_count = len(flat_pairs)
    if pair_count > BATCH_MAX_TOTAL_PAIRS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many total pairs. Maximum is {BATCH_MAX_TOTAL_PAIRS}",
        )

    model_pairs = truncate_pairs(flat_pairs, MAX_TEXT_CHARS)
    scores = _score_model_pairs(model_pairs, batch_size=BATCH_PAIR_SIZE)

    ranked_candidates: List[RankedCandidateResponse] = []
    cursor = 0
    for record in candidate_records:
        pair_ids = record["pair_ids"]
        candidate_scores = scores[cursor : cursor + len(pair_ids)]
        cursor += len(pair_ids)

        scored = {
            pair_id: score
            for pair_id, score in zip(pair_ids, candidate_scores)
        }
        overall = scored["overall"]
        group_scores = {group_name: score for group_name, score in scored.items() if group_name != "overall"}
        aggregate = aggregate_group_scores(
            _score_to_dict(overall),
            {group_name: _score_to_dict(score) for group_name, score in group_scores.items()},
        )
        ranked_candidates.append(
            RankedCandidateResponse(
                rank=0,
                candidate_id=record["candidate_id"],
                candidate_name=record["candidate_name"],
                overall=overall,
                group_scores=group_scores,
                final_score=aggregate["final_score"],
                label=aggregate["label"],
                best_groups=aggregate["best_groups"],
                weak_groups=aggregate["weak_groups"],
                ranking_raw_score=float(overall.raw_score),
                notes=FIT_NOTES,
            )
        )

    ranked_candidates.sort(
        key=lambda candidate: (
            -candidate.final_score,
            -candidate.ranking_raw_score,
            candidate.candidate_id,
        )
    )
    for rank, candidate in enumerate(ranked_candidates, start=1):
        candidate.rank = rank

    elapsed_ms = round((time.perf_counter() - started_at) * 1000)
    return BatchGroupScoreResponse(
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        device=reranker.device,
        candidate_count=len(candidate_records),
        pair_count=pair_count,
        batch_pair_size=BATCH_PAIR_SIZE,
        elapsed_ms=elapsed_ms,
        ranked_candidates=ranked_candidates,
    )


def _validate_rerank_request(request: RerankRequest) -> None:
    if not request.pairs:
        raise HTTPException(status_code=400, detail="pairs must not be empty")
    if len(request.pairs) > MAX_PAIRS:
        raise HTTPException(status_code=400, detail=f"Too many pairs. Maximum is {MAX_PAIRS}")

    for index, pair in enumerate(request.pairs):
        if not pair.pair_id.strip():
            raise HTTPException(status_code=400, detail=f"pairs[{index}].pair_id must not be empty")
        if not pair.query.strip():
            raise HTTPException(status_code=400, detail=f"pairs[{index}].query must not be empty")
        if not pair.document.strip():
            raise HTTPException(status_code=400, detail=f"pairs[{index}].document must not be empty")


def _score_to_dict(score: ScoreResult) -> Dict[str, float | int]:
    if hasattr(score, "model_dump"):
        return score.model_dump()
    return score.dict()


def _clean_cv_groups(cv_groups: Dict[str, str]) -> Dict[str, str]:
    return {
        group_name.strip(): group_text.strip()
        for group_name, group_text in cv_groups.items()
        if group_name and group_name.strip() and group_text and group_text.strip()
    }


def _score_model_pairs(
    model_pairs: Sequence[tuple[str, str]],
    batch_size: int | None = None,
) -> List[ScoreResult]:
    raw_scores, sigmoid_scores = _predict_model_pairs(model_pairs, batch_size=batch_size)
    return [
        _build_score_result(raw_score, sigmoid_score)
        for raw_score, sigmoid_score in zip(raw_scores, sigmoid_scores)
    ]


def _predict_model_pairs(
    model_pairs: Sequence[tuple[str, str]],
    batch_size: int | None = None,
) -> tuple[List[float], List[float]]:
    try:
        raw_scores, sigmoid_scores = reranker.predict_both(model_pairs, batch_size=batch_size)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected inference error: {exc}") from exc

    if len(raw_scores) != len(model_pairs) or len(sigmoid_scores) != len(model_pairs):
        raise HTTPException(status_code=500, detail="Unexpected inference error: score count mismatch")
    return raw_scores, sigmoid_scores


def _build_score_result(raw_score: float, sigmoid_score: float) -> ScoreResult:
    calibrated = calibrate_raw_score(raw_score, SCORE_TEMPERATURE)
    calibrated["sigmoid_score"] = float(sigmoid_score)
    return ScoreResult(**calibrated)


@app.post("/match-applications", response_model=MatchApplicationsResponse)
def match_applications(
    request: MatchApplicationsRequest, _: None = Depends(require_api_key)
) -> MatchApplicationsResponse:
    if not request.job_profile.criteria:
        raise HTTPException(status_code=400, detail="Job profile has no criteria")
    if not request.applications:
        raise HTTPException(status_code=400, detail="No applications provided")
    if len(request.applications) > MAX_CANDIDATES:
        raise HTTPException(
            status_code=400,
            detail=f"Too many applications. Maximum is {MAX_CANDIDATES}",
        )

    # 1. Build queries for all criteria
    criteria_queries = []
    for c in request.job_profile.criteria:
        query = f"[{c.importance.upper()}] {c.name}"
        if c.minimum_years:
            query += f" (Minimum {c.minimum_years} years)"
        if c.proficiency:
            query += f" ({c.proficiency})"
        query += f" - {c.source_text}"
        criteria_queries.append(query)

    # 2. Build evidence documents for all candidates
    candidate_evidences = []
    for app_req in request.applications:
        evidences = []
        for e in app_req.candidate_profile.evidence_items:
            doc = f"[{e.evidence_type}] {e.name}"
            if e.role:
                doc += f" - Role: {e.role}"
            if e.skills:
                doc += f" - Skills: {', '.join(e.skills)}"
            doc += f" - {e.source_text}"
            evidences.append((e.name, doc))
        candidate_evidences.append(evidences)

    # 3. Construct flattened pairs
    flat_pairs = []
    # keep track of where each candidate's scores start/end, and where each criterion's scores start/end
    candidate_offsets = []
    current_idx = 0

    for evidences in candidate_evidences:
        candidate_start = current_idx
        criterion_offsets = []
        for q in criteria_queries:
            crit_start = current_idx
            if not evidences:
                # If candidate has no evidence, we still need to record that they have 0 evidence items
                pass
            else:
                for _, doc in evidences:
                    flat_pairs.append((q, doc))
                    current_idx += 1
            criterion_offsets.append((crit_start, current_idx))
        candidate_offsets.append((candidate_start, current_idx, criterion_offsets))

    if len(flat_pairs) > BATCH_MAX_TOTAL_PAIRS:
         raise HTTPException(
            status_code=400,
            detail=f"Too many total pairs. Maximum is {BATCH_MAX_TOTAL_PAIRS}",
        )

    # 4. Batch Score
    scores = []
    if flat_pairs:
        model_pairs = truncate_pairs(flat_pairs, MAX_TEXT_CHARS)
        _, sigmoid_scores = _predict_model_pairs(model_pairs, batch_size=BATCH_PAIR_SIZE)
        scores = sigmoid_scores

    # 5. Reconstruct Results
    results = []
    for app_req, (_, _, crit_offsets), evidences in zip(
        request.applications, candidate_offsets, candidate_evidences
    ):
        crit_results = []
        for c_idx, (crit, (start, end)) in enumerate(
            zip(request.job_profile.criteria, crit_offsets)
        ):
            if start == end:
                # No evidence
                crit_results.append(
                    CriterionMatchResult(
                        criterion_index=c_idx,
                        criterion_name=crit.name,
                        criterion_source_text=crit.source_text,
                        importance=crit.importance,
                        status="not_matched",
                        explanation="Candidate provided no evidence.",
                    )
                )
                continue

            # Find best evidence
            crit_scores = scores[start:end]
            best_idx = max(range(len(crit_scores)), key=crit_scores.__getitem__)
            best_score = crit_scores[best_idx]
            best_evidence_name, best_evidence_doc = evidences[best_idx]

            if best_score >= RERANKER_MATCH_THRESHOLD:
                status = "matched"
                explanation = "Candidate evidence strongly matches the criterion."
            else:
                status = "not_matched"
                explanation = "Candidate evidence does not sufficiently match the criterion."

            crit_results.append(
                CriterionMatchResult(
                    criterion_index=c_idx,
                    criterion_name=crit.name,
                    criterion_source_text=crit.source_text,
                    importance=crit.importance,
                    status=status,
                    explanation=explanation,
                    evidence_text=best_evidence_doc,
                    evidence_name=best_evidence_name,
                    internal_evidence_score=float(best_score),
                )
            )

        results.append(
            CandidateMatchResult(
                application_id=app_req.application_id,
                criterion_results=crit_results,
            )
        )

    return MatchApplicationsResponse(
        model_name=MODEL_NAME,
        results=results,
    )

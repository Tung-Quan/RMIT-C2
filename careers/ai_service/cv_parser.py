"""CV parser service.

Orchestrates the full parsing pipeline for a CV:

    CVParsingInput
        -> prompt construction
        -> LLM generation
        -> JSON extraction
        -> Pydantic validation
        -> grounding validation
        -> post-processing
        -> CandidateProfile
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from ai_service.cv_prompt import build_parser_prompt, build_repair_prompt
from ai_service.cv_schemas import (
    CandidateEvidence,
    CandidateProfile,
    CVParsingInput,
)
from ai_service.job_parser import (
    EmptyModelOutputError,
    GroundingError,
    JobParserError,
    JsonExtractionError,
    MAX_RETRIES,
    SchemaValidationError,
    extract_json,
)
from ai_service.llm import JobParserLLM

logger = logging.getLogger(__name__)

@dataclass
class CVGroundingResult:
    accepted: list[CandidateEvidence] = field(default_factory=list)
    rejected: list[CandidateEvidence] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)

def _normalize_for_grounding(text: str) -> str:
    result = " ".join(text.lower().split())
    result = re.sub(r"[^\w\s]", " ", result)
    return " ".join(result.split())

def _is_grounded(source_text: str, corpus_parts: list[str]) -> bool:
    norm_source = _normalize_for_grounding(source_text)
    if not norm_source or len(norm_source) < 3:
        return False

    for part in corpus_parts:
        norm_part = _normalize_for_grounding(part)
        if norm_source in norm_part:
            return True

    source_words = set(norm_source.split())
    if len(source_words) < 2:
        return False

    for part in corpus_parts:
        part_words = set(_normalize_for_grounding(part).split())
        overlap = source_words & part_words
        if len(overlap) / len(source_words) >= 0.6:
            return True

    return False

def validate_cv_grounding(
    profile: CandidateProfile,
    cv: CVParsingInput,
) -> CVGroundingResult:
    corpus_parts = [cv.document_text]
    result = CVGroundingResult()

    for evidence in profile.evidence_items:
        if _is_grounded(evidence.source_text, corpus_parts):
            result.accepted.append(evidence)
        else:
            result.rejected.append(evidence)
            reason = f"Evidence '{evidence.name}' rejected: source_text not found in input"
            result.rejection_reasons.append(reason)
            logger.debug(reason)

    return result

def _evidence_dedup_key(e: CandidateEvidence) -> tuple:
    name = (e.canonical_name or e.name).strip().lower()
    return (
        e.evidence_type,
        name,
        e.organization.strip().lower() if e.organization else None,
        e.role.strip().lower() if e.role else None,
        e.start_date.strip().lower() if e.start_date else None,
        e.end_date.strip().lower() if e.end_date else None,
    )

def _deduplicate_evidence(
    evidence_items: list[CandidateEvidence],
) -> list[CandidateEvidence]:
    seen: set[tuple] = set()
    result: list[CandidateEvidence] = []
    for e in evidence_items:
        key = _evidence_dedup_key(e)
        if key not in seen:
            seen.add(key)
            result.append(e)
    return result

def _deduplicate_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result

def post_process_cv(
    profile: CandidateProfile,
    grounded_evidence: list[CandidateEvidence],
) -> CandidateProfile:
    return CandidateProfile(
        headline=profile.headline.strip() if profile.headline else None,
        summary=profile.summary.strip() if profile.summary else None,
        evidence_items=_deduplicate_evidence(grounded_evidence),
        search_keywords=_deduplicate_strings(profile.search_keywords),
    )

def parse_cv(
    cv: CVParsingInput,
    llm: JobParserLLM,
    max_retries: int = MAX_RETRIES,
) -> CandidateProfile:
    prompt = build_parser_prompt(cv)
    last_error = ""
    last_raw = ""

    for attempt in range(1 + max_retries):
        if attempt == 0:
            current_prompt = prompt
        else:
            logger.info("CV Parser retry %d/%d", attempt, max_retries)
            current_prompt = build_repair_prompt(last_raw, last_error)

        raw_output = llm.generate(current_prompt)
        last_raw = raw_output

        if not raw_output or not raw_output.strip():
            last_error = "Model returned empty output"
            if attempt < max_retries:
                continue
            raise EmptyModelOutputError(last_error)

        try:
            raw_json = extract_json(raw_output)
        except JsonExtractionError as exc:
            last_error = str(exc)
            if attempt < max_retries:
                continue
            raise

        try:
            profile = CandidateProfile.model_validate(raw_json)
        except ValidationError as exc:
            last_error = str(exc)
            if attempt < max_retries:
                continue
            raise SchemaValidationError(
                f"Schema validation failed: {exc}",
                raw_json=raw_json,
            ) from exc

        grounding = validate_cv_grounding(profile, cv)

        if grounding.rejected:
            logger.info(
                "CV Grounding rejected %d/%d evidence items",
                len(grounding.rejected),
                len(profile.evidence_items),
            )

        if len(cv.document_text) > 20 and not grounding.accepted and profile.evidence_items:
            last_error = "All evidence items were rejected by grounding validation."
            if attempt < max_retries:
                continue
            raise GroundingError(last_error)

        return post_process_cv(profile, grounding.accepted)

    raise JobParserError(f"CV parser exhausted all attempts. Last error: {last_error}")

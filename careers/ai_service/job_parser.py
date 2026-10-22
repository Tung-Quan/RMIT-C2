"""Job description parser service.

Orchestrates the full parsing pipeline:

    JobParsingInput
        -> prompt construction
        -> LLM generation
        -> JSON extraction
        -> Pydantic validation
        -> grounding validation
        -> post-processing
        -> ParsedJobProfile
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from pydantic import ValidationError

from ai_service.job_prompt import build_parser_prompt, build_repair_prompt
from ai_service.job_schemas import (
    JobCriterion,
    JobParsingInput,
    ParsedJobProfile,
)
from ai_service.llm import JobParserLLM

logger = logging.getLogger(__name__)

#: Maximum number of retry attempts after a failed parse.
MAX_RETRIES = 1


# -------------------------------------------------------------------
# Exceptions
# -------------------------------------------------------------------

class JobParserError(Exception):
    """Base exception for the job parser."""


class JsonExtractionError(JobParserError):
    """Raised when valid JSON cannot be extracted from LLM output."""


class SchemaValidationError(JobParserError):
    """Raised when the extracted JSON does not match ParsedJobProfile."""

    def __init__(self, message: str, raw_json: dict | None = None) -> None:
        super().__init__(message)
        self.raw_json = raw_json


class GroundingError(JobParserError):
    """Raised when no meaningful grounded criteria remain."""


class EmptyModelOutputError(JobParserError):
    """Raised when the LLM returns empty or whitespace-only output."""


# -------------------------------------------------------------------
# JSON extraction
# -------------------------------------------------------------------

# Pattern to detect and strip markdown JSON fences.
_MD_FENCE_RE = re.compile(
    r"```(?:json)?\s*\n?(.*?)\n?\s*```",
    re.DOTALL,
)


def extract_json(raw: str) -> dict:
    """Extract a single top-level JSON object from raw LLM output.

    Handles:
    - Markdown ``json`` code fences
    - Leading/trailing prose before/after the JSON object
    - Whitespace trimming

    Does NOT handle:
    - Python dict syntax (single quotes)
    - Multiple JSON objects
    - eval()-based parsing

    Raises
    ------
    JsonExtractionError
        If no valid JSON object can be found.
    """
    if not raw or not raw.strip():
        raise JsonExtractionError("Model returned empty output")

    text = raw.strip()

    # 1) Try stripping markdown fences.
    fence_match = _MD_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    # 2) Try parsing directly.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 3) Locate the first { ... } block.
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        candidate = text[brace_start : brace_end + 1]
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    raise JsonExtractionError(
        f"Could not extract valid JSON from model output "
        f"(length={len(raw)})"
    )


# -------------------------------------------------------------------
# Grounding validation
# -------------------------------------------------------------------

@dataclass
class GroundingResult:
    """Result of grounding validation."""

    accepted: list[JobCriterion] = field(default_factory=list)
    rejected: list[JobCriterion] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)


def _normalize_for_grounding(text: str) -> str:
    """Normalize text for fuzzy grounding comparison."""
    # Lowercase, collapse whitespace, strip punctuation at edges.
    result = " ".join(text.lower().split())
    result = re.sub(r"[^\w\s]", " ", result)
    return " ".join(result.split())


def _is_grounded(source_text: str, corpus_parts: list[str]) -> bool:
    """Check if source_text is approximately contained in the corpus.

    Uses a substring check after normalization.  This is intentionally
    conservative — the source text (normalized) should appear as a
    substring of at least one corpus part.
    """
    norm_source = _normalize_for_grounding(source_text)
    if not norm_source or len(norm_source) < 3:
        return False

    for part in corpus_parts:
        norm_part = _normalize_for_grounding(part)
        if norm_source in norm_part:
            return True

    # Also try checking if >60% of the words match in any part.
    source_words = set(norm_source.split())
    if len(source_words) < 2:
        # Single word — require exact substring.
        return False

    for part in corpus_parts:
        part_words = set(_normalize_for_grounding(part).split())
        overlap = source_words & part_words
        if len(overlap) / len(source_words) >= 0.6:
            return True

    return False


def validate_grounding(
    profile: ParsedJobProfile,
    job: JobParsingInput,
) -> GroundingResult:
    """Validate that each criterion's source_text is grounded in the input.

    Parameters
    ----------
    profile:
        The parsed profile from the LLM.
    job:
        The original cleaned job input.

    Returns
    -------
    GroundingResult
        Accepted and rejected criteria with reasons.
    """
    # Build the corpus from all input fields.
    corpus_parts: list[str] = []
    if job.description:
        corpus_parts.append(job.description)
    corpus_parts.extend(job.requirements)
    corpus_parts.extend(job.responsibilities)

    # Also join everything into one block for broader matching.
    full_corpus = " ".join(corpus_parts)
    corpus_parts.append(full_corpus)

    result = GroundingResult()

    for criterion in profile.criteria:
        if _is_grounded(criterion.source_text, corpus_parts):
            result.accepted.append(criterion)
        else:
            result.rejected.append(criterion)
            reason = (
                f"Criterion '{criterion.name}' rejected: "
                f"source_text not found in input"
            )
            result.rejection_reasons.append(reason)
            logger.debug(reason)

    return result


# -------------------------------------------------------------------
# Post-processing
# -------------------------------------------------------------------

def _criterion_dedup_key(c: JobCriterion) -> tuple:
    """Build a deduplication key for a criterion.

    Does NOT merge required/preferred variants with the same name.
    """
    name = (c.canonical_name or c.name).strip().lower()
    return (
        c.criterion_type,
        name,
        c.importance,
        c.minimum_years,
        (c.proficiency or "").strip().lower() or None,
    )


def _deduplicate_criteria(
    criteria: list[JobCriterion],
) -> list[JobCriterion]:
    """Remove exact duplicate criteria, preserving first-occurrence order."""
    seen: set[tuple] = set()
    result: list[JobCriterion] = []
    for c in criteria:
        key = _criterion_dedup_key(c)
        if key not in seen:
            seen.add(key)
            result.append(c)
    return result


def _deduplicate_strings(items: list[str]) -> list[str]:
    """Deduplicate strings case-insensitively, keeping first occurrence."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result


def post_process(
    profile: ParsedJobProfile,
    grounded_criteria: list[JobCriterion],
) -> ParsedJobProfile:
    """Apply deterministic post-processing to a parsed profile.

    - Trim text fields.
    - Deduplicate criteria, domains, keywords.
    - Normalize empty strings to None.
    """
    return ParsedJobProfile(
        normalized_title=profile.normalized_title.strip(),
        job_family=(
            profile.job_family.strip() if profile.job_family else None
        ) or None,
        seniority=(
            profile.seniority.strip() if profile.seniority else None
        ) or None,
        domains=_deduplicate_strings(profile.domains),
        criteria=_deduplicate_criteria(grounded_criteria),
        search_keywords=_deduplicate_strings(profile.search_keywords),
    )


# -------------------------------------------------------------------
# Main parser function
# -------------------------------------------------------------------

def parse_job(
    job: JobParsingInput,
    llm: JobParserLLM,
    max_retries: int = MAX_RETRIES,
) -> ParsedJobProfile:
    """Parse a job description into a structured profile.

    Parameters
    ----------
    job:
        Cleaned job parsing input.
    llm:
        An LLM client satisfying the ``JobParserLLM`` protocol.
    max_retries:
        Maximum retry attempts after validation failure.

    Returns
    -------
    ParsedJobProfile
        Validated, grounded, post-processed profile.

    Raises
    ------
    EmptyModelOutputError
        If the LLM returns empty output.
    JsonExtractionError
        If valid JSON cannot be extracted after retries.
    SchemaValidationError
        If the JSON does not match the schema after retries.
    GroundingError
        If no meaningful grounded criteria remain when the input
        contains requirements or responsibilities.
    """
    prompt = build_parser_prompt(job)
    last_error: str = ""
    last_raw: str = ""

    for attempt in range(1 + max_retries):
        if attempt == 0:
            current_prompt = prompt
        else:
            logger.info(
                "Parser retry %d/%d", attempt, max_retries
            )
            current_prompt = build_repair_prompt(last_raw, last_error)

        # --- Generate ---
        raw_output = llm.generate(current_prompt)
        last_raw = raw_output

        if not raw_output or not raw_output.strip():
            last_error = "Model returned empty output"
            if attempt < max_retries:
                continue
            raise EmptyModelOutputError(last_error)

        # --- Extract JSON ---
        try:
            raw_json = extract_json(raw_output)
        except JsonExtractionError as exc:
            last_error = str(exc)
            if attempt < max_retries:
                continue
            raise

        # --- Validate schema ---
        try:
            profile = ParsedJobProfile.model_validate(raw_json)
        except ValidationError as exc:
            last_error = str(exc)
            if attempt < max_retries:
                continue
            raise SchemaValidationError(
                f"Schema validation failed: {exc}",
                raw_json=raw_json,
            ) from exc

        # --- Grounding ---
        grounding = validate_grounding(profile, job)

        if grounding.rejected:
            logger.info(
                "Grounding rejected %d/%d criteria",
                len(grounding.rejected),
                len(profile.criteria),
            )
            for reason in grounding.rejection_reasons:
                logger.debug(reason)

        has_input_content = bool(
            job.requirements or job.responsibilities
        )

        if has_input_content and not grounding.accepted:
            last_error = (
                "All criteria were rejected by grounding validation. "
                "source_text values do not match input content."
            )
            if attempt < max_retries:
                continue
            raise GroundingError(last_error)

        # --- Post-process ---
        return post_process(profile, grounding.accepted)

    # Should not be reached, but just in case.
    raise JobParserError(
        f"Parser exhausted all attempts. Last error: {last_error}"
    )

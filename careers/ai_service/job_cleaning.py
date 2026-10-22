"""Deterministic text cleaning for job-parsing input.

This module performs safe, meaning-preserving transformations on raw
job-posting text before it reaches the LLM parser.  No inference,
summarization, or semantic normalization is performed here.

Design rules
------------
* Preserve original wording — especially qualifiers such as "is a plus",
  "at least", "preferred", "not required", years of experience, and
  proficiency levels.
* Never rewrite, translate, or classify content.
* Use only Python standard-library utilities.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Sequence


# ---------------------------------------------------------------------------
# Unicode whitespace normalization
# ---------------------------------------------------------------------------

# Characters that should be treated as ordinary spaces but are not ASCII 0x20.
_UNICODE_SPACE_RE = re.compile(
    r"[\u00A0\u2000-\u200A\u202F\u205F\u3000]",
)


def _normalize_unicode_whitespace(text: str) -> str:
    """Replace non-breaking and typographic spaces with regular spaces."""
    return _UNICODE_SPACE_RE.sub(" ", text)


# ---------------------------------------------------------------------------
# Line-ending normalization
# ---------------------------------------------------------------------------

def _normalize_line_endings(text: str) -> str:
    """Convert Windows (\\r\\n) and old Mac (\\r) endings to Unix (\\n)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ---------------------------------------------------------------------------
# Basic HTML stripping
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove HTML tags and decode common HTML entities.

    Only applied when the text looks like it contains HTML.  This avoids
    damaging plain-text angle-bracket usage such as ``<your-name>``.
    """
    # Quick heuristic: at least one opening+closing pair or self-closing tag.
    if not re.search(r"<\s*\w+[\s/>]", text):
        return text
    cleaned = _HTML_TAG_RE.sub("", text)
    cleaned = html.unescape(cleaned)
    return cleaned


# ---------------------------------------------------------------------------
# Bullet parsing
# ---------------------------------------------------------------------------

# Matches common bullet prefixes at the start of a line (after optional
# leading whitespace).  Handles:  - * • ‣ ▪ ◦ – — + and numbered forms
# like "1." or "1)".
_BULLET_RE = re.compile(
    r"^[ \t]*"
    r"(?:"
    r"[-*•‣▪◦–—+]"        # symbol bullets
    r"|"
    r"\d{1,3}[.)]\s"      # numbered bullets: "1. " or "1) "
    r")"
    r"[ \t]*",
    re.MULTILINE,
)


def _looks_like_bullet_list(text: str) -> bool:
    """Return True if the text appears to be a bullet list.

    Heuristic: at least two lines start with a recognised bullet marker.
    """
    matches = _BULLET_RE.findall(text)
    return len(matches) >= 2


def _split_bullets(text: str) -> list[str]:
    """Split bullet-pointed text into individual items.

    Each item is stripped of its leading bullet marker.  Empty items are
    discarded.
    """
    items: list[str] = []
    for line in text.split("\n"):
        stripped = _BULLET_RE.sub("", line).strip()
        if stripped:
            items.append(stripped)
    return items


# ---------------------------------------------------------------------------
# Semicolon list splitting
# ---------------------------------------------------------------------------

def _looks_like_semicolon_list(text: str) -> bool:
    """Return True when text is a single logical line with semicolons.

    Only triggers when there are at least two semicolons and no bullet
    markers, reducing false positives on prose that happens to contain a
    semicolon.
    """
    if "\n" in text.strip():
        return False
    return text.count(";") >= 2 and not _BULLET_RE.search(text)


def _split_semicolons(text: str) -> list[str]:
    """Split a semicolon-separated string into items."""
    return [item.strip() for item in text.split(";") if item.strip()]


# ---------------------------------------------------------------------------
# Deduplication (preserves original order)
# ---------------------------------------------------------------------------

def _deduplicate(items: Sequence[str]) -> list[str]:
    """Remove exact duplicate items while preserving first-occurrence order.

    Comparison is case-insensitive and whitespace-normalized so that
    ``"Python"`` and ``" python "`` are treated as duplicates, but the
    original casing of the first occurrence is kept.
    """
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = " ".join(item.lower().split())
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# Whitespace collapsing within a single item
# ---------------------------------------------------------------------------

def _collapse_internal_whitespace(text: str) -> str:
    """Collapse runs of spaces (not newlines) within a line to one space."""
    return re.sub(r"[ \t]+", " ", text)


# ---------------------------------------------------------------------------
# Public cleaning functions
# ---------------------------------------------------------------------------

def clean_text_block(text: str) -> str:
    """Clean a single multiline text field (description, etc.).

    Returns the cleaned text with normalized whitespace and line endings.
    Empty or whitespace-only input returns an empty string.
    """
    if not text or not text.strip():
        return ""

    result = strip_html(text)
    result = _normalize_line_endings(result)
    result = _normalize_unicode_whitespace(result)

    # Collapse excessive blank lines (3+ newlines → 2) while keeping
    # intentional paragraph breaks.
    result = re.sub(r"\n{3,}", "\n\n", result)

    # Per-line cleanup: trim trailing whitespace, collapse internal spaces.
    lines = [
        _collapse_internal_whitespace(line.rstrip())
        for line in result.split("\n")
    ]

    # Remove leading and trailing empty lines.
    result = "\n".join(lines).strip()

    return result


def clean_to_list(text: str) -> list[str]:
    """Convert a multiline or semicolon-separated field to a list of items.

    Each item is cleaned individually.  Exact duplicates are removed.
    Prose text (no bullets, no semicolons) is returned as a single-item
    list to avoid fragmenting sentences.
    """
    if not text or not text.strip():
        return []

    cleaned = strip_html(text)
    cleaned = _normalize_line_endings(cleaned)
    cleaned = _normalize_unicode_whitespace(cleaned)

    if _looks_like_bullet_list(cleaned):
        items = _split_bullets(cleaned)
    elif _looks_like_semicolon_list(cleaned):
        items = _split_semicolons(cleaned)
    else:
        # Plain prose — keep as single item.
        single = clean_text_block(text)
        return [single] if single else []

    # Per-item cleanup.
    items = [_collapse_internal_whitespace(item.strip()) for item in items]
    items = [item for item in items if item]
    items = _deduplicate(items)

    return items


def description_duplicates_title(
    description: str,
    job_title: str,
) -> bool:
    """Return True when the description is just a restatement of the title.

    This uses a conservative heuristic: the description — after stripping
    whitespace and lowering — must be *contained within* a trivial
    expansion of the title, or vice-versa, and must be short enough that
    it clearly adds no additional information.

    Examples that return True:
        title="Backend Developer Intern"
        description="Backend Developer Intern"

        title="Backend Developer Intern"
        description="We are looking for a Backend Developer Intern."

    Examples that return False:
        title="Backend Developer Intern"
        description="We are looking for a backend intern."
        (contains genuinely different wording that may add context)
    """
    if not description or not job_title:
        return False

    desc_norm = " ".join(description.lower().split())
    title_norm = " ".join(job_title.lower().split())

    # Exact match after normalization.
    if desc_norm == title_norm:
        return True

    # Very short description that is entirely contained in the title.
    if len(desc_norm) <= len(title_norm) + 5 and title_norm in desc_norm:
        return True

    # Description is just "We are looking for a <title>." or similar
    # trivial wrapper with no additional information.
    # Pattern: optional filler + title + optional punctuation.
    trivial_patterns = [
        # "Backend Developer Intern"
        re.compile(
            r"^" + re.escape(title_norm) + r"[.!]?$"
        ),
        # "We are looking for a Backend Developer Intern."
        re.compile(
            r"^we\s+are\s+(?:looking|searching|hiring)\s+"
            r"(?:for\s+)?(?:a\s+|an\s+)?"
            + re.escape(title_norm)
            + r"[.!]?$"
        ),
        # "Hiring: Backend Developer Intern"
        re.compile(
            r"^(?:hiring|opening|position|role)\s*:\s*"
            + re.escape(title_norm)
            + r"[.!]?$"
        ),
    ]
    for pattern in trivial_patterns:
        if pattern.match(desc_norm):
            return True

    return False

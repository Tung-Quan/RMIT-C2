"""Deterministic text cleaning for CV input."""

from ai_service.job_cleaning import clean_text_block

def clean_cv_text(text: str) -> str:
    """Clean the raw CV text.

    Normalizes whitespace and removes excessive blank lines.
    """
    return clean_text_block(text)

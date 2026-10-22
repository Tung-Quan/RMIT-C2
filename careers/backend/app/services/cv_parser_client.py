import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AICVParserError(Exception):
    """Base exception for CV parser client."""

    pass


class AICVParserUnavailableError(AICVParserError):
    """Raised when the AI service is unreachable or 503."""

    pass


class AICVParserTimeoutError(AICVParserError):
    """Raised when the AI service times out during inference."""

    pass


class AICVParserInvalidResponseError(AICVParserError):
    """Raised when the AI service returns 422 or unexpected format."""

    pass


async def parse_cv_document(document_text: str) -> dict:
    """
    Calls the AI service POST /parse-cv to extract a structured CandidateProfile.

    Args:
        document_text: The extracted CV text.

    Returns:
        A dictionary representing the CandidateProfile.
    """
    settings = get_settings()
    url = f"{settings.AI_SERVICE_BASE_URL.rstrip('/')}/parse-cv"
    headers = {}
    if settings.AI_SERVICE_API_KEY:
        headers["X-AI-Service-Key"] = settings.AI_SERVICE_API_KEY

    try:
        async with httpx.AsyncClient(timeout=settings.AI_SERVICE_PARSE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json={"document_text": document_text},
                headers=headers,
            )

            if response.status_code == 503:
                raise AICVParserUnavailableError(
                    "AI parser model is unavailable or failed to load."
                )
            elif response.status_code == 502:
                raise AICVParserError(
                    "AI parser failed to generate output (e.g., OOM or generation error)."
                )
            elif response.status_code == 422:
                raise AICVParserInvalidResponseError("Invalid input provided to AI parser.")

            response.raise_for_status()
            data = response.json()

            if not isinstance(data, dict) or "evidence_items" not in data:
                raise AICVParserInvalidResponseError(
                    "AI service returned malformed JSON structure."
                )

            return data

    except httpx.ReadTimeout as e:
        logger.error(f"Timeout connecting to AI service at {url}")
        raise AICVParserTimeoutError(
            f"AI parsing timed out after {settings.AI_SERVICE_PARSE_TIMEOUT_SECONDS}s."
        ) from e
    except httpx.RequestError as e:
        logger.error(f"Error connecting to AI service at {url}: {e}")
        raise AICVParserUnavailableError("Failed to connect to AI service.") from e
    except Exception as e:
        if isinstance(e, AICVParserError):
            raise
        logger.error(f"Unexpected error when calling AI service: {e}")
        raise AICVParserError(f"Unexpected error during CV parsing: {str(e)}") from e

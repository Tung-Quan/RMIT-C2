import logging

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class AIJobParserError(Exception):
    """Base exception for job parser client."""

    pass


class AIJobParserUnavailableError(AIJobParserError):
    """Raised when the AI service is unreachable or 503."""

    pass


class AIJobParserTimeoutError(AIJobParserError):
    """Raised when the AI service times out during inference."""

    pass


class AIJobParserInvalidResponseError(AIJobParserError):
    """Raised when the AI service returns 422 or unexpected format."""

    pass


async def parse_job_description(raw_job_payload: dict) -> dict:
    """
    Calls the AI service POST /parse-job to extract a structured profile.

    Args:
        raw_job_payload: A dictionary matching the AI service RawJobCreate schema.

    Returns:
        A dictionary representing the ParsedJobProfile.
    """
    settings = get_settings()
    url = f"{settings.AI_SERVICE_BASE_URL.rstrip('/')}/parse-job"
    headers = {}
    if settings.AI_SERVICE_API_KEY:
        headers["X-AI-Service-Key"] = settings.AI_SERVICE_API_KEY

    try:
        async with httpx.AsyncClient(timeout=settings.AI_SERVICE_PARSE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=raw_job_payload, headers=headers)

            if response.status_code == 503:
                raise AIJobParserUnavailableError(
                    "AI parser model is unavailable or failed to load."
                )
            elif response.status_code == 502:
                raise AIJobParserError(
                    "AI parser failed to generate output (e.g., OOM or generation error)."
                )
            elif response.status_code == 422:
                raise AIJobParserInvalidResponseError("Invalid input provided to AI parser.")

            response.raise_for_status()
            data = response.json()

            # Very basic validation to ensure it looks like a ParsedJobProfile
            if not isinstance(data, dict) or "criteria" not in data:
                raise AIJobParserInvalidResponseError(
                    "AI service returned malformed JSON structure."
                )

            return data

    except httpx.ReadTimeout as e:
        logger.error(f"Timeout connecting to AI service at {url}")
        raise AIJobParserTimeoutError(
            f"AI parsing timed out after {settings.AI_SERVICE_PARSE_TIMEOUT_SECONDS}s."
        ) from e
    except httpx.RequestError as e:
        logger.error(f"Error connecting to AI service at {url}: {e}")
        raise AIJobParserUnavailableError("Failed to connect to AI service.") from e
    except Exception as e:
        if isinstance(e, AIJobParserError):
            raise
        logger.error(f"Unexpected error when calling AI service: {e}")
        raise AIJobParserError(f"Unexpected error during parsing: {str(e)}") from e

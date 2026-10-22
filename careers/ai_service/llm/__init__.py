"""LLM client interface and Qwen implementation for job parsing."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class JobParserLLM(Protocol):
    """Protocol for generative LLM clients used by the job parser.

    Any object implementing ``generate(prompt) -> str`` satisfies this
    protocol, enabling easy testing with fake/mock clients.
    """

    def generate(self, prompt: str) -> str:
        """Send a prompt and return the raw model response text."""
        ...


# Re-export the concrete Qwen client for convenience.
# Importing is lazy — the module does NOT load torch at import time.
from ai_service.llm.qwen_client import QwenGenerativeClient  # noqa: E402

__all__ = ["JobParserLLM", "QwenGenerativeClient"]

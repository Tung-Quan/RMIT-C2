"""Qwen generative LLM client for job description parsing.

This client uses the ``transformers`` library to run a local Qwen
instruction-tuned model.  It is intentionally separate from the Qwen
*reranker* client in ``ai_service/qwen_reranker.py``.

Model weights are NOT loaded at import time.  The client lazily
initialises on first ``generate()`` call or when ``load()`` is called
explicitly.

Configuration
-------------
Environment variables (all optional, sensible defaults provided):

    JOB_PARSER_MODEL
        HuggingFace model ID or local path.
        Relative paths are resolved from the project root (the
        directory containing ``ai_service/``).
        Default: ``./models/qwen3-4b-instruct``

    JOB_PARSER_DEVICE
        ``auto`` | ``cuda`` | ``cpu``.
        Default: ``auto``

    JOB_PARSER_DTYPE
        ``auto`` | ``float16`` | ``bfloat16`` | ``float32``.
        Default: ``auto`` (resolves to ``bfloat16``)

    JOB_PARSER_MAX_NEW_TOKENS
        Maximum tokens to generate.
        Default: ``2048``

    JOB_PARSER_ALLOW_DOWNLOAD
        Set to ``true`` to allow downloading from HuggingFace Hub.
        By default, only local model files are used.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = "./models/qwen3-4b-instruct"
_DEFAULT_DEVICE = "auto"
_DEFAULT_DTYPE = "auto"
_DEFAULT_MAX_NEW_TOKENS = 2048

# ---------------------------------------------------------------------------
# Project root detection
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Locate the project root by searching upward for ``ai_service/``.

    Falls back to the current working directory if the marker is not
    found (e.g. when running from an unusual location).
    """
    # Start from the directory containing *this* file:
    #   ai_service/llm/qwen_client.py  →  ai_service/llm/  →  ai_service/  →  root
    here = Path(__file__).resolve().parent  # ai_service/llm/
    candidate = here.parent.parent          # project root
    if (candidate / "ai_service").is_dir():
        return candidate
    # Fallback: cwd.
    return Path.cwd()


def _resolve_model_path(raw_path: str) -> str:
    """Resolve a possibly-relative model path against the project root.

    Absolute paths and HuggingFace Hub IDs (e.g. ``Qwen/Qwen3-4B``)
    are returned unchanged.
    """
    p = Path(raw_path)
    if p.is_absolute():
        return raw_path
    # Heuristic: Hub IDs contain a slash but no backslash and no dots
    # at the start.  Local relative paths start with "./" or are plain
    # directory names.
    if "/" in raw_path and not raw_path.startswith(("./", "../")):
        # Looks like a Hub ID — return as-is.
        return raw_path
    resolved = _find_project_root() / p
    return str(resolved)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ModelLoadError(Exception):
    """Raised when the parser model or tokenizer cannot be loaded."""


class ModelGenerationError(Exception):
    """Raised when text generation fails at runtime."""


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class QwenGenerativeClient:
    """Lazy-loading Qwen generative client for structured JSON extraction.

    Satisfies the :class:`~ai_service.llm.JobParserLLM` protocol.
    """

    def __init__(
        self,
        model_path: str | None = None,
        device: str | None = None,
        dtype: str | None = None,
        max_new_tokens: int | None = None,
    ) -> None:
        raw_path = (
            model_path
            or os.getenv("JOB_PARSER_MODEL", _DEFAULT_MODEL_PATH)
        )
        self.model_path = _resolve_model_path(raw_path)

        self._device_setting = (
            device
            or os.getenv("JOB_PARSER_DEVICE", _DEFAULT_DEVICE)
        )
        self._dtype_setting = (
            dtype
            or os.getenv("JOB_PARSER_DTYPE", _DEFAULT_DTYPE)
        )
        self.max_new_tokens = (
            max_new_tokens
            if max_new_tokens is not None
            else int(
                os.getenv(
                    "JOB_PARSER_MAX_NEW_TOKENS",
                    str(_DEFAULT_MAX_NEW_TOKENS),
                )
            )
        )
        self._allow_download = (
            os.getenv("JOB_PARSER_ALLOW_DOWNLOAD", "").strip().lower()
            == "true"
        )

        self._model: Any = None
        self._tokenizer: Any = None

    # ----- properties -------------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """Return True when the model and tokenizer are ready."""
        return self._model is not None

    # ----- loading ----------------------------------------------------------

    def load(self) -> None:
        """Load model and tokenizer.  Safe to call multiple times."""
        if self._model is not None:
            return

        # Late import to avoid loading torch at module import time.
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ModelLoadError(
                f"Required package not installed: {exc}"
            ) from exc

        resolved_device = self._resolve_device(self._device_setting)
        resolved_dtype = self._resolve_dtype(self._dtype_setting)
        local_only = not self._allow_download

        logger.info(
            "Loading generative parser model (device=%s, dtype=%s, "
            "local_only=%s)",
            resolved_device,
            resolved_dtype,
            local_only,
        )
        logger.info("Model path: %s", self.model_path)

        t0 = time.perf_counter()

        try:
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_path,
                local_files_only=local_only,
            )
        except Exception as exc:
            raise ModelLoadError(
                f"Failed to load tokenizer from {self.model_path}: {exc}"
            ) from exc

        device_map = "auto" if resolved_device == "cuda" else resolved_device
        quantization = {}
        if os.getenv("JOB_PARSER_LOAD_IN_4BIT", "false").lower() == "true":
            if resolved_device != "cuda":
                raise ModelLoadError("The configured 4-bit parser requires CUDA")
            from transformers import BitsAndBytesConfig
            quantization["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
            )
            device_map = {"": 0}

        try:
            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                local_files_only=local_only,
                device_map=device_map,
                dtype=resolved_dtype,
                **quantization,
            )
            self._model.eval()
        except Exception as exc:
            self._tokenizer = None
            msg = str(exc)
            if "CUDA out of memory" in msg or "OutOfMemoryError" in msg:
                raise ModelLoadError(
                    f"GPU out of memory loading {self.model_path}. "
                    f"Try JOB_PARSER_DEVICE=cpu or a smaller model."
                ) from exc
            raise ModelLoadError(
                f"Failed to load model from {self.model_path}: {exc}"
            ) from exc

        elapsed = time.perf_counter() - t0
        logger.info(
            "Generative parser model loaded in %.1f s", elapsed
        )

    # ----- generation -------------------------------------------------------

    def generate(self, prompt: str) -> str:
        """Generate a completion from the given prompt.

        The model is loaded lazily on first call if not already loaded.

        Parameters
        ----------
        prompt:
            The full prompt text.  Will be split into a system
            instruction and user content at the ``--- JOB POSTING ---``
            marker if present, otherwise sent as a single user message.

        Returns
        -------
        str
            Raw model response text (newly generated tokens only).

        Raises
        ------
        ModelGenerationError
            On any runtime generation failure including CUDA OOM.
        """
        if self._model is None:
            self.load()

        # Late import kept consistent with load().
        import torch

        messages = self._build_messages(prompt)

        try:
            inputs = self._tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self._model.device)
        except Exception as exc:
            raise ModelGenerationError(
                f"Tokenization failed: {exc}"
            ) from exc

        try:
            with torch.inference_mode():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                    repetition_penalty=1.05,
                    pad_token_id=self._tokenizer.eos_token_id,
                )
        except Exception as exc:
            msg = str(exc)
            if "CUDA out of memory" in msg or "OutOfMemoryError" in msg:
                raise ModelGenerationError(
                    "GPU out of memory during generation. "
                    "Try a shorter prompt or JOB_PARSER_DEVICE=cpu."
                ) from exc
            raise ModelGenerationError(
                f"Model generation failed: {exc}"
            ) from exc

        # Decode only the newly generated tokens (exclude the prompt).
        prompt_length = inputs["input_ids"].shape[-1]
        generated_ids = outputs[0][prompt_length:]
        result = self._tokenizer.decode(
            generated_ids,
            skip_special_tokens=True,
        ).strip()

        if not result:
            logger.warning("Model returned empty output")

        return result

    # ----- internal helpers -------------------------------------------------

    @staticmethod
    def _build_messages(prompt: str) -> list[dict[str, str]]:
        """Split a prompt into system + user messages for the chat template.

        If the prompt contains the ``--- JOB POSTING ---`` marker the
        text before it becomes the system instruction and the text from
        the marker onward becomes the user message.  Otherwise the
        entire prompt is sent as a single user message.
        """
        marker = "--- JOB POSTING ---"
        idx = prompt.find(marker)
        if idx > 0:
            system_part = prompt[:idx].strip()
            user_part = prompt[idx:].strip()
            return [
                {"role": "system", "content": system_part},
                {"role": "user", "content": user_part},
            ]
        return [{"role": "user", "content": prompt}]

    @staticmethod
    def _resolve_device(setting: str) -> str:
        """Resolve the device setting to a concrete device string."""
        import torch

        normalised = setting.strip().lower()
        if normalised not in {"auto", "cuda", "cpu"}:
            raise ValueError(
                f"JOB_PARSER_DEVICE must be one of: auto, cuda, cpu "
                f"(got '{setting}')"
            )
        if normalised == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if normalised == "cuda" and not torch.cuda.is_available():
            raise ValueError(
                "JOB_PARSER_DEVICE=cuda requested but CUDA is not "
                "available"
            )
        return normalised

    @staticmethod
    def _resolve_dtype(setting: str) -> "Any":
        """Resolve the dtype setting to a torch dtype."""
        import torch

        normalised = setting.strip().lower()
        mapping = {
            "auto": torch.bfloat16,
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }
        if normalised not in mapping:
            raise ValueError(
                f"JOB_PARSER_DTYPE must be one of: "
                f"auto, float16, bfloat16, float32 (got '{setting}')"
            )
        return mapping[normalised]

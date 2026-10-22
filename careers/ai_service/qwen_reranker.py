"""Model loading and batch prediction for Qwen3-Reranker."""

from __future__ import annotations

import os
from typing import List, Sequence

import torch
from sentence_transformers import CrossEncoder


MODEL_NAME = "Qwen3-Reranker"
MODEL_VERSION = "qwen3-reranker-0.6b"
DEFAULT_MODEL_PATH = "./models/qwen3-reranker-0.6b"
DEFAULT_PROMPT_NAME = "cv_job_match"
DEFAULT_PROMPT = (
    "Judge whether the candidate CV text is semantically relevant and suitable for "
    "the job description. Consider skills, projects, work evidence, education or "
    "training, and transferable evidence. Do not rely only on exact keyword overlap. "
    "Return a relevance score for how well the CV evidence matches the job."
)


class QwenReranker:
    def __init__(
        self,
        model_path: str | None = None,
        device_setting: str | None = None,
        prompt: str = DEFAULT_PROMPT,
    ) -> None:
        self.model_path = model_path or os.getenv("QWEN_RERANKER_MODEL_PATH", DEFAULT_MODEL_PATH)
        self.device = self._resolve_device(device_setting or os.getenv("QWEN_RERANKER_DEVICE", "auto"))
        self.prompt = prompt
        self.model: CrossEncoder | None = None

    @staticmethod
    def _resolve_device(device_setting: str) -> str:
        normalized = device_setting.strip().lower()
        if normalized not in {"auto", "cuda", "cpu"}:
            raise ValueError("QWEN_RERANKER_DEVICE must be one of: auto, cuda, cpu")
        if normalized == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if normalized == "cuda" and not torch.cuda.is_available():
            raise ValueError("QWEN_RERANKER_DEVICE=cuda was requested, but CUDA is not available")
        return normalized

    @property
    def model_loaded(self) -> bool:
        return self.model is not None

    @property
    def gpu_name(self) -> str | None:
        if self.device == "cuda" and torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
        return None

    def load(self) -> None:
        if self.model is not None:
            return

        print(f"[ai_service] Loading {MODEL_NAME} from {self.model_path}")
        print(f"[ai_service] Device: {self.device}")
        if self.gpu_name:
            print(f"[ai_service] GPU: {self.gpu_name}")

        self.model = CrossEncoder(
            self.model_path,
            prompts={DEFAULT_PROMPT_NAME: self.prompt},
            default_prompt_name=DEFAULT_PROMPT_NAME,
            device=self.device,
        )
        print("[ai_service] Model loaded")

    def _predict_chunk(self, pairs: Sequence[tuple[str, str]], activation) -> List[float]:
        if self.model is None:
            self.load()
        if self.model is None:
            raise RuntimeError("Model failed to load")

        try:
            scores = self.model.predict(
                list(pairs),
                activation_fct=activation,
                convert_to_numpy=True,
            )
        except TypeError:
            scores = self.model.predict(
                list(pairs),
                activation_fn=activation,
                convert_to_numpy=True,
            )
        return _to_float_list(scores)

    def predict_raw(self, pairs: Sequence[tuple[str, str]], batch_size: int | None = None) -> List[float]:
        return self._predict_chunks(pairs, torch.nn.Identity(), batch_size)

    def predict_sigmoid(self, pairs: Sequence[tuple[str, str]], batch_size: int | None = None) -> List[float]:
        return self._predict_chunks(pairs, torch.nn.Sigmoid(), batch_size)

    def predict_both(
        self,
        pairs: Sequence[tuple[str, str]],
        batch_size: int | None = None,
    ) -> tuple[List[float], List[float]]:
        normalized_pairs = list(pairs)
        if not normalized_pairs:
            return [], []

        chunk_size = _resolve_batch_size(batch_size, len(normalized_pairs))
        raw_scores: List[float] = []
        sigmoid_scores: List[float] = []
        for chunk in _chunks(normalized_pairs, chunk_size):
            raw_scores.extend(self._predict_chunk(chunk, torch.nn.Identity()))
            sigmoid_scores.extend(self._predict_chunk(chunk, torch.nn.Sigmoid()))
        return raw_scores, sigmoid_scores

    def _predict_chunks(
        self,
        pairs: Sequence[tuple[str, str]],
        activation,
        batch_size: int | None,
    ) -> List[float]:
        normalized_pairs = list(pairs)
        if not normalized_pairs:
            return []

        chunk_size = _resolve_batch_size(batch_size, len(normalized_pairs))
        scores: List[float] = []
        for chunk in _chunks(normalized_pairs, chunk_size):
            scores.extend(self._predict_chunk(chunk, activation))
        return scores


def _resolve_batch_size(batch_size: int | None, pair_count: int) -> int:
    if batch_size is None or batch_size <= 0:
        return pair_count
    return min(batch_size, pair_count)


def _chunks(pairs: Sequence[tuple[str, str]], chunk_size: int) -> List[Sequence[tuple[str, str]]]:
    return [pairs[start : start + chunk_size] for start in range(0, len(pairs), chunk_size)]


def _to_float_list(scores) -> List[float]:
    if hasattr(scores, "detach"):
        scores = scores.detach().cpu().numpy()
    if hasattr(scores, "tolist"):
        scores = scores.tolist()
    if isinstance(scores, (int, float)):
        return [float(scores)]
    if isinstance(scores, list):
        return [_first_float(score) for score in scores]
    return [float(scores)]


def _first_float(value) -> float:
    if isinstance(value, list):
        if not value:
            return 0.0
        return _first_float(value[0])
    return float(value)

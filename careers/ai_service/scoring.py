"""Score calibration and CV group aggregation helpers."""

from __future__ import annotations

import math
from statistics import mean
from typing import Dict, Iterable, List, Mapping, Sequence


MIN_DISPLAY_SCORE = 1
MAX_DISPLAY_SCORE = 95
DEFAULT_SCORE_TEMPERATURE = 3.0


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def clamp_int(value: int, minimum: int = MIN_DISPLAY_SCORE, maximum: int = MAX_DISPLAY_SCORE) -> int:
    return max(minimum, min(maximum, value))


def calibrate_raw_score(raw_score: float, temperature: float) -> Dict[str, float | int]:
    safe_temperature = temperature if temperature > 0 else DEFAULT_SCORE_TEMPERATURE
    sigmoid_score = sigmoid(raw_score)
    calibrated_score = sigmoid(raw_score / safe_temperature)
    display_score = clamp_int(round(calibrated_score * 100))
    return {
        "raw_score": float(raw_score),
        "sigmoid_score": float(sigmoid_score),
        "calibrated_score": float(calibrated_score),
        "display_score": display_score,
    }


def label_from_final_score(final_score: int) -> str:
    if final_score >= 85:
        return "strong_fit"
    if final_score >= 70:
        return "moderate_fit"
    if final_score >= 55:
        return "weak_fit"
    return "lower_priority"


def join_cv_groups(cv_groups: Mapping[str, str]) -> str:
    return "\n\n".join(
        f"[CV GROUP: {group_name.upper()}]\n{group_text.strip()}"
        for group_name, group_text in cv_groups.items()
        if group_text and group_text.strip()
    )


def average_top_scores(scores: Sequence[float], count: int = 2) -> float:
    top_scores = sorted(scores, reverse=True)[:count]
    if not top_scores:
        return 0.0
    return mean(top_scores)


def aggregate_group_scores(
    overall_score: Mapping[str, float | int],
    group_scores: Mapping[str, Mapping[str, float | int]],
) -> Dict[str, object]:
    group_values = list(group_scores.values())
    top_group_average = average_top_scores(
        [float(score["calibrated_score"]) for score in group_values],
        count=2,
    )
    final_calibrated = 0.70 * float(overall_score["calibrated_score"]) + 0.30 * top_group_average
    final_score = clamp_int(round(final_calibrated * 100))

    sorted_groups = sorted(
        group_scores.items(),
        key=lambda item: float(item[1]["raw_score"]),
        reverse=True,
    )

    return {
        "final_score": final_score,
        "label": label_from_final_score(final_score),
        "best_groups": [group_name for group_name, _ in sorted_groups[:2]],
        "weak_groups": [
            group_name
            for group_name, score in group_scores.items()
            if float(score["calibrated_score"]) < 0.55
        ],
    }


def truncate_text(value: str, max_chars: int) -> str:
    return value[:max_chars] if len(value) > max_chars else value


def truncate_pairs(
    pairs: Iterable[tuple[str, str]],
    max_chars: int,
) -> List[tuple[str, str]]:
    return [
        (truncate_text(query, max_chars), truncate_text(document, max_chars))
        for query, document in pairs
    ]

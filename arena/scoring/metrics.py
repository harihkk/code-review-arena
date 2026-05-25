"""Deterministic benchmark metric formulas."""

from __future__ import annotations


def precision(true_positives: int, false_positives: int) -> float:
    denominator = true_positives + false_positives
    return true_positives / denominator if denominator else 0.0


def recall(true_positives: int, false_negatives: int) -> float:
    denominator = true_positives + false_negatives
    return true_positives / denominator if denominator else 0.0


def f_beta_score(value_precision: float, value_recall: float, beta: float = 1.0) -> float:
    if value_precision == 0 and value_recall == 0:
        return 0.0
    beta_squared = beta**2
    return (
        (1 + beta_squared)
        * value_precision
        * value_recall
        / (beta_squared * value_precision + value_recall)
    )


def rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None

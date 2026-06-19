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


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score confidence interval for a binomial proportion (default 95%).

    Returns None when there is nothing to estimate (total == 0). The interval is
    deliberately wide at small n: 7/10 is not [0.70, 0.70] but roughly [0.40, 0.89],
    so two reviewers whose intervals overlap are not reliably ranked.
    """
    if total <= 0:
        return None
    p_hat = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    center = (p_hat + z2 / (2 * total)) / denominator
    margin = z * ((p_hat * (1 - p_hat) / total + z2 / (4 * total * total)) ** 0.5) / denominator
    return round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)

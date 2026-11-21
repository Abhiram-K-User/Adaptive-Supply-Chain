"""Auditable evaluation metrics; undefined comparisons return None, never success."""
from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np


def _finite(values: Sequence[float]) -> np.ndarray:
    result = np.asarray(values, dtype=float)
    if result.ndim != 1 or not len(result) or not np.isfinite(result).all():
        raise ValueError("Expected a nonempty finite one-dimensional sample")
    return result


def auroc(labels: Sequence[int], scores: Sequence[float]) -> float | None:
    """Pairwise concordance, half credit for ties; undefined for one class."""
    values = _finite(scores)
    y = np.asarray(labels)
    if len(y) != len(values) or not np.isin(y, [0, 1]).all():
        raise ValueError("Labels must be aligned binary outcomes")
    positive, negative = values[y == 1], values[y == 0]
    if not len(positive) or not len(negative):
        return None
    return float(np.mean([(np.mean(p > negative) + .5 * np.mean(p == negative)) for p in positive]))


def ece(labels: Sequence[int], probabilities: Sequence[float], bins: int = 10) -> float:
    p = _finite(probabilities)
    y = np.asarray(labels)
    if bins < 1 or len(y) != len(p) or not np.isin(y, [0, 1]).all() or (p < 0).any() or (p > 1).any():
        raise ValueError("ECE requires aligned binary labels and probabilities in [0,1]")
    indices = np.minimum((p * bins).astype(int), bins - 1)
    return float(sum(np.mean(indices == i) * abs(np.mean(p[indices == i]) - np.mean(y[indices == i]))
                     for i in range(bins) if (indices == i).any()))


def weighted_cvar(costs: Sequence[float], probabilities: Sequence[float], alpha: float = .95) -> float:
    values, weights = _finite(costs), _finite(probabilities)
    if len(values) != len(weights) or (weights < 0).any() or weights.sum() <= 0 or not 0 <= alpha < 1:
        raise ValueError("Invalid CVaR sample, weights or quantile")
    weights = weights / weights.sum()
    tail, total = 1 - alpha, 0.0
    for i in np.argsort(-values, kind="stable"):
        take = min(tail, float(weights[i]))
        total += take * values[i]
        tail -= take
        if tail <= 1e-12:
            break
    return float(total / (1 - alpha))


def mean_ci(values: Sequence[float], *, seed: int = 42, samples: int = 1000) -> dict:
    x = _finite(values)
    if samples < 1:
        raise ValueError("Bootstrap sample count must be positive")
    rng = np.random.default_rng(seed)
    means = np.asarray([rng.choice(x, len(x), replace=True).mean() for _ in range(samples)])
    return {"mean": float(x.mean()), "ci95": [float(np.quantile(means, .025)), float(np.quantile(means, .975))],
            "n": len(x), "bootstrap_samples": samples}


def reduction(baseline: float, candidate: float) -> float | None:
    if not math.isfinite(baseline) or not math.isfinite(candidate):
        raise ValueError("Nonfinite comparison")
    return (baseline - candidate) / baseline if baseline > 0 else None


def pareto_frontier(points: Sequence[dict]) -> list[dict]:
    """Keep nondominated measured cost/regret points without interpolation."""
    return [p for p in points if not any(q["cost"] <= p["cost"] and q["regret"] <= p["regret"]
            and (q["cost"] < p["cost"] or q["regret"] < p["regret"]) for q in points)]

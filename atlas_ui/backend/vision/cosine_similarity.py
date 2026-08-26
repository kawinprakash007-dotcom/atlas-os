"""
Validated cosine similarity utilities for face recognition.

For two L2-normalized embedding vectors, cosine similarity equals the dot product.
All functions here validate inputs and clamp outputs to [-1, 1].
"""
from typing import List, Optional
from dataclasses import dataclass
import numpy as np


class CosineSimilarityError(ValueError):
    """Raised when similarity cannot be computed safely."""


@dataclass
class SimilarityResult:
    """Structured result of a cosine similarity template search."""
    best_similarity: float
    matched_template_index: int


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """
    Computes cosine similarity between two L2-normalized embedding vectors.

    Validates:
    - Dimension match
    - Both arrays are finite (no NaN / inf)
    - Both vectors have unit norm (within tolerance — they must be pre-normalized)
    - Result is clamped to [-1.0, 1.0]

    Args:
        a: L2-normalized embedding vector
        b: L2-normalized embedding vector

    Returns:
        float in [-1.0, 1.0]

    Raises:
        CosineSimilarityError: on invalid input
    """
    arr_a = np.array(a, dtype=np.float64)
    arr_b = np.array(b, dtype=np.float64)

    if arr_a.ndim != 1 or arr_b.ndim != 1:
        raise CosineSimilarityError(
            f"Embeddings must be 1-D arrays; got shapes {arr_a.shape} and {arr_b.shape}"
        )

    if arr_a.shape[0] != arr_b.shape[0]:
        raise CosineSimilarityError(
            f"Dimension mismatch: {arr_a.shape[0]} vs {arr_b.shape[0]}"
        )

    if not np.isfinite(arr_a).all():
        raise CosineSimilarityError("Embedding 'a' contains NaN or infinite values.")

    if not np.isfinite(arr_b).all():
        raise CosineSimilarityError("Embedding 'b' contains NaN or infinite values.")

    norm_a = float(np.linalg.norm(arr_a))
    norm_b = float(np.linalg.norm(arr_b))

    NORM_TOL = 0.01  # vectors must be within 1% of unit norm
    if abs(norm_a - 1.0) > NORM_TOL:
        raise CosineSimilarityError(
            f"Embedding 'a' is not unit-normalized: norm={norm_a:.6f}"
        )
    if abs(norm_b - 1.0) > NORM_TOL:
        raise CosineSimilarityError(
            f"Embedding 'b' is not unit-normalized: norm={norm_b:.6f}"
        )

    raw = float(np.dot(arr_a, arr_b))
    return float(np.clip(raw, -1.0, 1.0))


def best_cosine_similarity(
    probe: List[float],
    templates: List[List[float]],
) -> SimilarityResult:
    """
    Compares a probe embedding against all templates and returns the best match.

    Returns:
        SimilarityResult containing best_similarity and matched_template_index.

    Raises:
        CosineSimilarityError: if probe or any template is invalid
    """
    if not templates:
        raise CosineSimilarityError("Template list is empty.")

    best_sim = -2.0
    best_idx = -1

    for idx, template in enumerate(templates):
        sim = cosine_similarity(probe, template)
        if sim > best_sim:
            best_sim = sim
            best_idx = idx

    return SimilarityResult(best_similarity=best_sim, matched_template_index=best_idx)

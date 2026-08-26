import pytest
import numpy as np
from atlas_ui.backend.vision.cosine_similarity import (
    cosine_similarity,
    best_cosine_similarity,
    CosineSimilarityError,
    SimilarityResult
)

def test_best_cosine_similarity_returns_dataclass():
    """Verify that the interface returns a SimilarityResult and handles matching correctly."""
    probe = [1.0, 0.0]
    templates = [
        [0.0, 1.0],  # orthogonal
        [1.0, 0.0],  # match
        [-1.0, 0.0]  # opposite
    ]
    
    result = best_cosine_similarity(probe, templates)
    
    assert isinstance(result, SimilarityResult)
    assert result.best_similarity == 1.0
    assert result.matched_template_index == 1

def test_best_cosine_similarity_empty_templates():
    """Verify that empty templates raise a safe CosineSimilarityError."""
    with pytest.raises(CosineSimilarityError, match="Template list is empty"):
        best_cosine_similarity([1.0, 0.0], [])

def test_cosine_similarity_invalid_norm():
    """Verify vectors that are not unit normalized raise errors."""
    with pytest.raises(CosineSimilarityError, match="not unit-normalized"):
        cosine_similarity([10.0, 0.0], [1.0, 0.0])

def test_cosine_similarity_invalid_nan():
    """Verify NaN embeddings raise errors."""
    with pytest.raises(CosineSimilarityError, match="contains NaN or infinite"):
        cosine_similarity([float('nan'), 0.0], [1.0, 0.0])

def test_cosine_similarity_invalid_dim():
    """Verify mismatched dimensions raise errors."""
    with pytest.raises(CosineSimilarityError, match="Dimension mismatch"):
        cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])

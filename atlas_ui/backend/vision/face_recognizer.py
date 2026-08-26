from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List
import numpy as np

@dataclass
class FaceEmbeddingResult:
    """
    Result of a face recognition embedding generation attempt.
    """
    success: bool
    embedding: Optional[List[float]] = None
    error: Optional[str] = None
    embedding_dimension: int = 0

class FaceRecognizer(ABC):
    """
    Abstract interface for generating deep-learning face embeddings.

    encode() receives:
        frame  — the full BGR camera frame (H x W x 3)
        bbox   — [x1, y1, x2, y2] bounding box from YOLO (integers, pixel coords)

    This allows implementations to run their own internal landmark detection or
    alignment models on the full frame rather than on a small bounding-box crop.
    Returning a FaceEmbeddingResult with success=True means the embedding is
    512-D, L2-normalized (norm ≈ 1.0), and all values are finite.
    """
    @abstractmethod
    def encode(self, frame: np.ndarray, bbox: List[int]) -> FaceEmbeddingResult:
        """
        Accepts a full BGR frame and a YOLO face bounding box.
        Returns a 512-D L2-normalized face embedding or a failure result.
        """
        pass

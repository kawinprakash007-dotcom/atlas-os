from dataclasses import dataclass
from typing import List

@dataclass
class FaceDetection:
    """
    Represents a single detected face bounding box and its confidence score.
    """
    bbox: List[int]  # [x1, y1, x2, y2]
    confidence: float

@dataclass
class FaceDetectionResult:
    """
    Encapsulates results from a single face detection run.
    Provides convenience properties for status checking.
    """
    faces: List[FaceDetection]
    face_count: int

    @property
    def no_face(self) -> bool:
        return self.face_count == 0

    @property
    def single_face(self) -> bool:
        return self.face_count == 1

    @property
    def multiple_faces(self) -> bool:
        return self.face_count > 1

    @property
    def status(self) -> str:
        if self.no_face:
            return "NO_FACE"
        elif self.single_face:
            return "SINGLE_FACE"
        else:
            return "MULTIPLE_FACES"

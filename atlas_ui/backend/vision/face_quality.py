import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Optional

from atlas_ui.backend.vision import config

@dataclass
class FaceQualityResult:
    """
    Quality checking outcome for a cropped face region.
    """
    accepted: bool
    reason: Optional[str] = None
    face_width: int = 0
    face_height: int = 0
    blur_score: float = 0.0
    brightness_score: float = 0.0

def validate_face_quality(frame: np.ndarray, bbox: List[int]) -> FaceQualityResult:
    """
    Validates crop boundaries, face dimensions, focus/blur, and lighting intensity.
    """
    # 0. Basic validation
    if frame is None or frame.size == 0:
        return FaceQualityResult(accepted=False, reason="Invalid or empty input frame.")
    
    if len(bbox) != 4:
        return FaceQualityResult(accepted=False, reason="Bounding box must contain exactly 4 coordinates.")

    x1, y1, x2, y2 = bbox
    frame_h, frame_w = frame.shape[:2]

    # 1. Boundary check: Check if coordinates are within the image dimensions
    if x1 < 0 or y1 < 0 or x2 > frame_w or y2 > frame_h or x1 >= x2 or y1 >= y2:
        return FaceQualityResult(
            accepted=False,
            reason=f"Face bounding box {bbox} is out of frame boundaries (height={frame_h}, width={frame_w}).",
            face_width=max(0, x2 - x1),
            face_height=max(0, y2 - y1)
        )

    face_w = x2 - x1
    face_h = y2 - y1

    # 2. Size validation
    if face_w < config.MIN_FACE_WIDTH or face_h < config.MIN_FACE_HEIGHT:
        return FaceQualityResult(
            accepted=False,
            reason=f"Face dimensions {face_w}x{face_h} are below minimum threshold {config.MIN_FACE_WIDTH}x{config.MIN_FACE_HEIGHT}.",
            face_width=face_w,
            face_height=face_h
        )

    # Crop gray region for quality computations
    try:
        crop = frame[y1:y2, x1:x2]
        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    except Exception as e:
        return FaceQualityResult(accepted=False, reason=f"Failed to crop face region: {e}")

    if gray_crop.size == 0:
        return FaceQualityResult(accepted=False, reason="Cropped face region is empty.")

    # 3. Blur detection (Laplacian Variance)
    try:
        laplacian_var = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
    except Exception as e:
        laplacian_var = 0.0
        print(f"[QUALITY] Laplacian variance calculation failed: {e}", flush=True)

    if laplacian_var < config.MIN_BLUR_LAPLACIAN_VAR:
        return FaceQualityResult(
            accepted=False,
            reason=f"Face image is too blurry. Variance of Laplacian ({laplacian_var:.2f}) < threshold ({config.MIN_BLUR_LAPLACIAN_VAR}).",
            face_width=face_w,
            face_height=face_h,
            blur_score=laplacian_var
        )

    # 4. Brightness check (Mean pixel intensity)
    brightness = float(np.mean(gray_crop))
    if brightness < config.MIN_BRIGHTNESS:
        return FaceQualityResult(
            accepted=False,
            reason=f"Face region is too dark. Average brightness ({brightness:.2f}) < threshold ({config.MIN_BRIGHTNESS}).",
            face_width=face_w,
            face_height=face_h,
            blur_score=laplacian_var,
            brightness_score=brightness
        )
    
    if brightness > config.MAX_BRIGHTNESS:
        return FaceQualityResult(
            accepted=False,
            reason=f"Face region is too bright. Average brightness ({brightness:.2f}) > threshold ({config.MAX_BRIGHTNESS}).",
            face_width=face_w,
            face_height=face_h,
            blur_score=laplacian_var,
            brightness_score=brightness
        )

    # All checks passed successfully
    return FaceQualityResult(
        accepted=True,
        face_width=face_w,
        face_height=face_h,
        blur_score=laplacian_var,
        brightness_score=brightness
    )

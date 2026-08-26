import pytest
import numpy as np
import cv2

from atlas_ui.backend.vision.face_quality import validate_face_quality, FaceQualityResult
from atlas_ui.backend.vision import config

def test_face_quality_boundary_checks():
    # Frame size 100x100
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    
    # 1. Out of bounds (negative coords)
    res_neg = validate_face_quality(frame, [-10, 10, 50, 50])
    assert res_neg.accepted is False
    assert "boundaries" in res_neg.reason

    # 2. Out of bounds (exceed frame size)
    res_exceed = validate_face_quality(frame, [10, 10, 110, 50])
    assert res_exceed.accepted is False
    assert "boundaries" in res_exceed.reason

    # 3. Invalid box (width/height <= 0)
    res_inv = validate_face_quality(frame, [50, 50, 40, 40])
    assert res_inv.accepted is False


def test_face_quality_size_checks():
    # Frame size 500x500
    frame = np.zeros((500, 500, 3), dtype=np.uint8)
    
    # Box is 50x50 (below MIN_FACE_WIDTH/HEIGHT of 80)
    res = validate_face_quality(frame, [10, 10, 60, 60])
    assert res.accepted is False
    assert "below minimum threshold" in res.reason


def test_face_quality_brightness_checks():
    # Sharp checkerboard to bypass blur check, but let's make it extremely dark (mean ~ 10.0)
    dark_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    # Put checkerboard lines with low intensity
    dark_crop[0::10, :] = 20
    dark_crop[:, 0::10] = 20
    
    # Big frame containing the crop
    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    frame[50:150, 50:150] = dark_crop
    
    # Verify dark rejection
    res_dark = validate_face_quality(frame, [50, 50, 150, 150])
    assert res_dark.accepted is False
    assert "too dark" in res_dark.reason

    # Let's make it extremely bright (mean ~ 240.0) with some checkerboard texture to pass blur check
    bright_crop = np.ones((100, 100, 3), dtype=np.uint8) * 230
    bright_crop[0::10, :] = 250
    bright_crop[:, 0::10] = 250
    
    frame_bright = np.zeros((300, 300, 3), dtype=np.uint8)
    frame_bright[50:150, 50:150] = bright_crop
    
    # Verify bright rejection
    res_bright = validate_face_quality(frame_bright, [50, 50, 150, 150])
    assert res_bright.accepted is False
    assert "too bright" in res_bright.reason



def test_face_quality_blur_checks():
    # Sharp crop: high-frequency checkerboard pattern (high Laplacian variance)
    sharp_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    for i in range(100):
        for j in range(100):
            if (i // 5 + j // 5) % 2 == 0:
                sharp_crop[i, j] = [120, 120, 120]
            else:
                sharp_crop[i, j] = [60, 60, 60]

    # Blur crop: smooth gradient (low Laplacian variance)
    blur_crop = np.zeros((100, 100, 3), dtype=np.uint8)
    for i in range(100):
        blur_crop[i, :] = [100 + int(i * 0.2)] * 3

    # Big frames
    frame_sharp = np.zeros((300, 300, 3), dtype=np.uint8)
    frame_sharp[50:150, 50:150] = sharp_crop

    frame_blur = np.zeros((300, 300, 3), dtype=np.uint8)
    frame_blur[50:150, 50:150] = blur_crop

    # Sharp verification: should pass
    res_sharp = validate_face_quality(frame_sharp, [50, 50, 150, 150])
    assert res_sharp.accepted is True
    
    # Blur verification: should fail
    res_blur = validate_face_quality(frame_blur, [50, 50, 150, 150])
    assert res_blur.accepted is False
    assert "too blurry" in res_blur.reason

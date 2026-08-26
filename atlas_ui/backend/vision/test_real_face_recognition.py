"""
ATLAS OS — Real Face Recognition Diagnostic Validator

Runs four mandatory tests in sequence:
  TEST 1 — ENROLLED PERSON (expect MATCH)
  TEST 2 — DIFFERENT PERSON (expect REJECT)
  TEST 3 — NO FACE (expect REJECT, reason=NO_FACE)
  TEST 4 — MULTIPLE FACES (expect REJECT, reason=MULTIPLE_FACES)

Each test opens a fresh camera session (hardware buffer flushed on open),
collects VERIFY_OBSERVATION_FRAMES accepted embeddings, and decides on
MEDIAN similarity — so a single stale frame cannot cause a false match.

Additionally runs an OFFLINE INTRA vs CROSS SIMILARITY diagnostic using
the stored enrollment templates.
"""

import sys
import hashlib
import numpy as np

from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.arcface_recognizer import ArcFaceRecognizer
from atlas_ui.backend.vision.face_template_store import FaceTemplateStore
from atlas_ui.backend.vision.face_enrollment_service import FaceEnrollmentService
from atlas_ui.backend.vision.face_verification_service import FaceVerificationService
from atlas_ui.backend.vision import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def wait_for_enter(prompt: str) -> None:
    print(f"\n[PROMPT] {prompt}", flush=True)
    input("Press ENTER to proceed...")


def section(title: str) -> None:
    print(f"\n{'='*50}", flush=True)
    print(title, flush=True)
    print('='*50, flush=True)


def print_result(label: str, res) -> None:
    print(f"Verified       : {res.verified}", flush=True)
    print(f"Best similarity: {res.best_similarity:.4f}", flush=True)
    print(f"Faces detected : {res.faces_detected}", flush=True)
    print(f"Result         : {'MATCH' if res.verified else 'REJECT'}", flush=True)
    print(f"Reason         : {res.reason}", flush=True)
    if res.error:
        print(f"Error          : {res.error}", flush=True)


def run_offline_intra_cross_similarity(store: FaceTemplateStore, person_id: str) -> None:
    """
    Computes pairwise cosine similarity between enrolled templates.
    Intra-person: similarity between different samples of the same person.
    This confirms the enrollment templates form a tight cluster.
    """
    section("OFFLINE: INTRA-PERSON SIMILARITY (sanity check)")
    templates = store.get_templates(person_id)
    n = len(templates)
    if n < 2:
        print(f"[OFFLINE] Only {n} template — cannot compute intra-person similarity.", flush=True)
        return

    arrs = [np.array(t) for t in templates]
    sims = []
    for i in range(n):
        for j in range(i + 1, n):
            sim = float(np.dot(arrs[i], arrs[j]))
            sims.append(sim)
            print(f"  template[{i}] vs template[{j}] similarity = {sim:.4f}", flush=True)

    print(f"\n  Intra-person mean   : {np.mean(sims):.4f}", flush=True)
    print(f"  Intra-person median : {np.median(sims):.4f}", flush=True)
    print(f"  Intra-person min    : {np.min(sims):.4f}", flush=True)
    print(f"  Intra-person max    : {np.max(sims):.4f}", flush=True)


def capture_one_embedding(
    recognizer: ArcFaceRecognizer,
    detector: YOLOFaceDetector,
    label: str,
    flush_count: int = 5,
) -> np.ndarray | None:
    """
    Captures one frame, detects one face, returns its L2-normalized embedding.
    Returns None on any failure.
    """
    print(f"[CAPTURE] Opening camera for '{label}' embedding...", flush=True)
    with CameraManager(camera_index=0) as cam:
        # extra flush — guarantees fresh content
        cam.flush_frames(flush_count)
        frame = cam.capture_frame()

    fp = hashlib.md5(frame.tobytes()).hexdigest()[:12]
    print(f"[FRAME] shape={frame.shape}  fingerprint={fp}", flush=True)

    det = detector.detect(frame)
    print(f"[DETECTION] face_count={det.face_count}", flush=True)
    if det.face_count != 1:
        print(f"[CAPTURE] FAIL — expected 1 face, got {det.face_count}", flush=True)
        return None

    face = det.faces[0]
    x1, y1, x2, y2 = face.bbox
    crop = frame[y1:y2, x1:x2]
    crop_fp = hashlib.md5(crop.tobytes()).hexdigest()[:12]
    print(f"[FACE CROP] shape={crop.shape}  fingerprint={crop_fp}", flush=True)

    emb_res = recognizer.encode(crop)
    if not emb_res.success or emb_res.embedding is None:
        print(f"[CAPTURE] FAIL — encode error: {emb_res.error}", flush=True)
        return None

    arr = np.array(emb_res.embedding)
    emb_fp = hashlib.md5(arr.tobytes()).hexdigest()[:12]
    print(
        f"[EMBEDDING] dim={emb_res.embedding_dimension}  "
        f"norm={np.linalg.norm(arr):.6f}  fingerprint={emb_fp}", flush=True
    )
    return arr


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    section("ATLAS OS — Real Face Recognition Diagnostic Validator")

    detector = YOLOFaceDetector()
    recognizer = ArcFaceRecognizer()
    store = FaceTemplateStore()
    enroll_service = FaceEnrollmentService(detector, recognizer, store)
    verify_service = FaceVerificationService(detector, recognizer, store)

    person_id = "test-operator-1"

    # --- Ensure enrollment exists ---
    if not store.has_templates(person_id):
        print(f"\n[ENROLLMENT] No templates found for '{person_id}'. Initiating enrollment...", flush=True)
        wait_for_enter("Ensure EXACTLY ONE face is in view.")
        res = enroll_service.enroll_from_camera(person_id, camera_index=0, overwrite=True)
        if not res.success:
            print(f"[ERROR] Enrollment failed: {res.reason} ({res.error})", flush=True)
            sys.exit(1)
        print("[ENROLLMENT] Enrollment completed successfully!", flush=True)
    else:
        count = len(store.get_templates(person_id))
        print(f"\n[ENROLLMENT] Existing enrollment found for '{person_id}' with {count} templates.", flush=True)

    # --- Offline intra-person similarity diagnostic ---
    run_offline_intra_cross_similarity(store, person_id)

    # -----------------------------------------------------------------------
    # TEST 1 — ENROLLED PERSON
    # -----------------------------------------------------------------------
    wait_for_enter("TEST 1: ENROLLED PERSON — Look directly at the camera.")
    section("TEST 1: ENROLLED PERSON")

    res1 = verify_service.verify_from_camera(person_id, camera_index=0, timeout_seconds=15.0, verbose=True)
    print_result("ENROLLED PERSON", res1)

    # -----------------------------------------------------------------------
    # TEST 2 — DIFFERENT PERSON
    # -----------------------------------------------------------------------
    wait_for_enter(
        "TEST 2: DIFFERENT PERSON — Present a DIFFERENT person's face. "
        "Their fingerprints and similarity MUST be different from the enrolled person."
    )

    # Capture one offline embedding of the different person for cross-similarity logging
    print("\n[OFFLINE CROSS] Capturing ONE embedding of the different person...", flush=True)
    cross_emb = capture_one_embedding(recognizer, detector, label="different-person")
    if cross_emb is not None:
        templates = store.get_templates(person_id)
        cross_sims = [float(np.dot(cross_emb, np.array(t))) for t in templates]
        print(f"[OFFLINE CROSS] Cross-person similarities vs enrolled templates: "
              f"{[round(s,4) for s in cross_sims]}", flush=True)
        print(f"[OFFLINE CROSS] Cross-person max similarity: {max(cross_sims):.4f}", flush=True)
        print(f"[OFFLINE CROSS] Current FACE_MATCH_THRESHOLD: {config.FACE_MATCH_THRESHOLD}", flush=True)

    section("TEST 2: DIFFERENT PERSON")
    res2 = verify_service.verify_from_camera(person_id, camera_index=0, timeout_seconds=10.0, verbose=True)
    print_result("DIFFERENT PERSON", res2)

    # -----------------------------------------------------------------------
    # TEST 3 — NO FACE
    # -----------------------------------------------------------------------
    wait_for_enter(
        "TEST 3: NO FACE — Move completely out of the camera frame. "
        "No person should be visible."
    )
    section("TEST 3: NO FACE")

    res3 = verify_service.verify_from_camera(person_id, camera_index=0, timeout_seconds=5.0, verbose=True)
    print_result("NO FACE", res3)

    # Validate expectations
    if res3.verified:
        print("[FAIL] NO FACE test returned MATCH — UNEXPECTED!", flush=True)
    elif "NO_FACE" in (res3.reason or ""):
        print("[PASS] NO FACE test correctly returned REJECT with reason NO_FACE.", flush=True)
    else:
        print(f"[WARN] NO FACE test returned REJECT but reason was '{res3.reason}'", flush=True)

    # -----------------------------------------------------------------------
    # TEST 4 — MULTIPLE FACES
    # -----------------------------------------------------------------------
    wait_for_enter(
        "TEST 4: MULTIPLE FACES — Bring TWO faces into the camera frame simultaneously."
    )
    section("TEST 4: MULTIPLE FACES")

    res4 = verify_service.verify_from_camera(person_id, camera_index=0, timeout_seconds=5.0, verbose=True)
    print_result("MULTIPLE FACES", res4)

    # Validate expectations
    if res4.verified:
        print("[FAIL] MULTIPLE FACES test returned MATCH — UNEXPECTED!", flush=True)
    elif "MULTIPLE_FACES" in (res4.reason or ""):
        print("[PASS] MULTIPLE FACES test correctly returned REJECT with reason MULTIPLE_FACES.", flush=True)
    else:
        print(f"[WARN] MULTIPLE FACES test returned REJECT but reason was '{res4.reason}'", flush=True)

    # -----------------------------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------------------------
    section("FINAL SUMMARY")
    passed = 0
    total = 4

    def check(label, result, expect_verified, expect_reason_contains=None):
        nonlocal passed
        ok = result.verified == expect_verified
        if expect_reason_contains and ok:
            ok = expect_reason_contains in (result.reason or "")
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(
            f"  [{status}] {label:<30} verified={result.verified}  "
            f"similarity={result.best_similarity:.4f}  reason={result.reason}",
            flush=True
        )

    check("TEST 1 — Enrolled Person", res1, expect_verified=True)
    check("TEST 2 — Different Person", res2, expect_verified=False)
    check("TEST 3 — No Face", res3, expect_verified=False, expect_reason_contains="NO_FACE")
    check("TEST 4 — Multiple Faces", res4, expect_verified=False, expect_reason_contains="MULTIPLE_FACES")

    print(f"\n  Result: {passed}/{total} tests passed.", flush=True)

    if passed == total:
        print("\n[SYSTEM] All diagnostic tests PASSED. Pipeline is secure.", flush=True)
    else:
        print(
            "\n[SYSTEM] Some tests FAILED. "
            "Do NOT proceed to Phase 4 until all 4 tests pass.", flush=True
        )


if __name__ == "__main__":
    main()

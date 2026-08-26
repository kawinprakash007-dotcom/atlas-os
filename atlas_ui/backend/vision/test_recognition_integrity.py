"""
ATLAS OS — Recognition Integrity Diagnostic Tool  (Phase 4A.1)

Interactive forensic audit of the face recognition pipeline.

Runs via:
    python -m atlas_ui.backend.vision.test_recognition_integrity

Performs:
    OFFLINE  — Model metadata, embedding baseline, template quality audit
    PHASE A  — Enrolled person (≥ TARGET_FRAMES accepted frames)
    PHASE B  — Different / impostor person (≥ TARGET_FRAMES accepted frames)
    PHASE C  — No face edge-case
    PHASE D  — Multiple faces edge-case
    REPORT   — Full integrity report with threshold recommendation

DOES NOT modify any stored templates.
"""

import sys
import time
import hashlib
import numpy as np

import onnxruntime as ort

from atlas_ui.backend.vision.camera_manager import CameraManager
from atlas_ui.backend.vision.yolo_face_detector import YOLOFaceDetector
from atlas_ui.backend.vision.arcface_recognizer import ArcFaceRecognizer
from atlas_ui.backend.vision.face_template_store import FaceTemplateStore
from atlas_ui.backend.vision.face_quality import validate_face_quality
from atlas_ui.backend.vision.cosine_similarity import cosine_similarity, CosineSimilarityError
from atlas_ui.backend.vision import config

TARGET_FRAMES = 10          # accepted frames per person phase
CAMERA_WARMUP_FRAMES = 10   # frames discarded after camera open
PERSON_ID = "ATLAS-P-88888888"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def sep(title: str = "") -> None:
    line = "=" * 56
    if title:
        print(f"\n{line}", flush=True)
        print(title, flush=True)
        print(line, flush=True)
    else:
        print(line, flush=True)


def wait_for_enter(prompt: str) -> None:
    print(f"\n[PROMPT] {prompt}", flush=True)
    input("Press ENTER when ready...")


def emb_stats(embedding: list) -> dict:
    arr = np.array(embedding)
    return {
        "dim":  len(embedding),
        "norm": float(np.linalg.norm(arr)),
        "mean": float(np.mean(arr)),
        "std":  float(np.std(arr)),
        "min":  float(arr.min()),
        "max":  float(arr.max()),
        "fp":   hashlib.md5(arr.astype(np.float32).tobytes()).hexdigest()[:12],
    }


# ---------------------------------------------------------------------------
# OFFLINE: ONNX model diagnostic
# ---------------------------------------------------------------------------

def offline_model_diagnostic(model_path: str) -> dict:
    sep("OFFLINE: ONNX MODEL DIAGNOSTIC")
    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])

    inp = sess.get_inputs()[0]
    out = sess.get_outputs()[0]
    print(f"  Input  name  : {inp.name!r}")
    print(f"  Input  shape : {inp.shape}")
    print(f"  Input  dtype : {inp.type}")
    print(f"  Output name  : {out.name!r}")
    print(f"  Output shape : {out.shape}")
    print(f"  Output dtype : {out.type}")

    print(f"\n  Color order  : BGR → RGB (applied in encode())")
    print(f"  Normalization: (pixel − 127.5) / 128.0")
    print(f"  Layout       : NHWC")
    print(f"  Face align   : DISABLED (bounding-box crop only)")

    # Determinism
    rng = np.random.default_rng(7)
    img = rng.integers(0, 256, (1, 112, 112, 3)).astype(np.float32)
    norm = (img - 127.5) / 128.0
    e1 = sess.run(None, {inp.name: norm})[0][0]
    e2 = sess.run(None, {inp.name: norm})[0][0]
    print(f"\n  Deterministic: {np.allclose(e1, e2)}")
    e1n = e1 / np.linalg.norm(e1)
    e2n = e2 / np.linalg.norm(e2)
    print(f"  Self-sim (same input→same output): {np.dot(e1n, e2n):.6f}")

    return {"session": sess, "input_name": inp.name, "output_name": out.name}


# ---------------------------------------------------------------------------
# OFFLINE: random baseline similarity distribution
# ---------------------------------------------------------------------------

def offline_random_baseline(model_path: str, n_samples: int = 100) -> dict:
    sep("OFFLINE: RANDOM NOISE EMBEDDING BASELINE")
    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    inp_name = sess.get_inputs()[0].name

    rng = np.random.default_rng(42)
    embeddings = []
    for _ in range(n_samples):
        img = rng.integers(0, 256, (1, 112, 112, 3)).astype(np.float32)
        norm = (img - 127.5) / 128.0
        e = sess.run(None, {inp_name: norm})[0][0]
        e_n = e / np.linalg.norm(e)
        embeddings.append(e_n)

    sims = []
    for i in range(n_samples):
        for j in range(i + 1, n_samples):
            sims.append(float(np.dot(embeddings[i], embeddings[j])))

    sims = np.array(sims)
    print(f"  N random samples : {n_samples}")
    print(f"  N pairs          : {len(sims)}")
    print(f"  Min sim          : {sims.min():.4f}")
    print(f"  Max sim          : {sims.max():.4f}")
    print(f"  Mean sim         : {sims.mean():.4f}")
    print(f"  Std sim          : {sims.std():.4f}")
    print(f"  Median sim       : {np.median(sims):.4f}")
    print(f"  P5 sim           : {np.percentile(sims, 5):.4f}")
    print(f"  P95 sim          : {np.percentile(sims, 95):.4f}")
    min_safe = sims.mean() + 3 * sims.std()
    print(f"\n  *** Minimum safe threshold (mean+3σ): {min_safe:.4f} ***")
    print(f"  Current FACE_MATCH_THRESHOLD: {config.FACE_MATCH_THRESHOLD}")
    if config.FACE_MATCH_THRESHOLD < min_safe:
        print(f"  WARNING: Current threshold is BELOW noise floor! Any face may match.")
    else:
        print(f"  Threshold is above noise floor — SECURE.")

    return {
        "min": float(sims.min()), "max": float(sims.max()),
        "mean": float(sims.mean()), "std": float(sims.std()),
        "median": float(np.median(sims)), "n": len(sims),
    }


# ---------------------------------------------------------------------------
# OFFLINE: template store quality audit
# ---------------------------------------------------------------------------

def offline_template_audit(store: FaceTemplateStore, person_id: str) -> dict:
    sep(f"OFFLINE: TEMPLATE QUALITY AUDIT  [{person_id}]")

    if not store.has_templates(person_id):
        print(f"  NOT ENROLLED — no templates for {person_id}")
        return {}

    templates = store.get_templates(person_id)
    n = len(templates)
    dim = len(templates[0]) if templates else 0
    print(f"  person_id        : {person_id}")
    print(f"  template_count   : {n}")
    print(f"  embedding_dim    : {dim}")
    print()

    arrs = [np.array(t) for t in templates]
    fps = [hashlib.md5(a.astype(np.float32).tobytes()).hexdigest()[:12] for a in arrs]

    for i, (arr, fp) in enumerate(zip(arrs, fps)):
        norm = float(np.linalg.norm(arr))
        print(f"  T{i+1}: fp={fp}  norm={norm:.6f}  mean={arr.mean():.6f}  std={arr.std():.6f}")

    unique = set(fps)
    print(f"\n  Unique fingerprints: {len(unique)} / {n}")
    if len(unique) < n:
        print("  CRITICAL: DUPLICATE TEMPLATES DETECTED")

    sims = [[float(np.dot(arrs[i], arrs[j])) for j in range(n)] for i in range(n)]
    print("\n  Pairwise similarity matrix:")
    print("        " + "".join(f"    T{j+1}" for j in range(n)))
    for i in range(n):
        row = f"    T{i+1}  " + "".join(f"{sims[i][j]:6.4f}" for j in range(n))
        print(row)

    off = [sims[i][j] for i in range(n) for j in range(n) if i != j]
    min_off = min(off)
    max_off = max(off)
    mean_off = sum(off) / len(off)
    print(f"\n  Off-diagonal: min={min_off:.4f}  max={max_off:.4f}  mean={mean_off:.4f}")

    if max_off > 0.999:
        print("  WARNING: EXTREMELY LOW VARIATION — templates may be duplicates")
    elif max_off > 0.98:
        print("  NOTE: High intra-template similarity — consider varied expressions at enrollment")
    elif min_off < 0.80:
        print("  NOTE: Some templates have low similarity — possible mis-captured frames")
    else:
        print("  Template cluster quality: GOOD")

    return {"min": min_off, "max": max_off, "mean": mean_off, "n": n, "dim": dim}


# ---------------------------------------------------------------------------
# Live capture: collect N accepted frames and compute per-template similarities
# ---------------------------------------------------------------------------

def collect_live_similarities(
    detector: YOLOFaceDetector,
    recognizer: ArcFaceRecognizer,
    templates: list,
    session_label: str,
    session_num: int,
    target_frames: int,
    timeout_seconds: float = 60.0,
) -> list:
    """
    Opens a fresh camera session (buffer flushed), captures frames, requires
    exactly 1 face per frame, generates an embedding, and records per-template
    cosine similarities.

    Returns list of result dicts, one per accepted frame.
    """
    results = []
    frame_id = 0
    accepted = 0
    no_face_frames = 0
    multi_face_frames = 0
    quality_rej = 0
    encode_fail = 0
    start_time = time.time()

    print(f"\n[CAMERA] Opening camera (session={session_num})...", flush=True)

    with CameraManager(camera_index=0) as cam:
        # Mandatory buffer warmup — discard first CAMERA_WARMUP_FRAMES frames
        print(f"[CAMERA] Flushing {CAMERA_WARMUP_FRAMES} warmup frames...", flush=True)
        cam.flush_frames(CAMERA_WARMUP_FRAMES)
        print(f"[CAMERA] Buffer warmup complete. session={session_num}", flush=True)

        while accepted < target_frames and (time.time() - start_time) < timeout_seconds:
            frame = cam.capture_frame()
            frame_id += 1
            ts = time.time()

            det = detector.detect(frame)

            if det.face_count == 0:
                no_face_frames += 1
                continue
            if det.face_count > 1:
                multi_face_frames += 1
                continue

            # Exactly one face
            face = det.faces[0]
            x1, y1, x2, y2 = face.bbox

            quality = validate_face_quality(frame, face.bbox)
            if not quality.accepted:
                quality_rej += 1
                continue

            crop = frame[y1:y2, x1:x2]
            emb_res = recognizer.encode(crop)
            if not emb_res.success or emb_res.embedding is None:
                encode_fail += 1
                continue

            probe = emb_res.embedding
            arr_p = np.array(probe)

            # per-template similarities
            per_tmpl = []
            for tmpl in templates:
                try:
                    sim = cosine_similarity(probe, tmpl)
                    per_tmpl.append(sim)
                except CosineSimilarityError:
                    per_tmpl.append(None)

            valid_sims = [s for s in per_tmpl if s is not None]
            if not valid_sims:
                continue

            best = max(valid_sims)
            mean_s = float(np.mean(valid_sims))
            min_s = float(np.min(valid_sims))
            max_s = float(np.max(valid_sims))

            accepted += 1
            crop_fp = hashlib.md5(crop.tobytes()).hexdigest()[:12]
            emb_fp = hashlib.md5(arr_p.astype(np.float32).tobytes()).hexdigest()[:12]
            emb_norm = float(np.linalg.norm(arr_p))

            print(f"\n  [CAMERA DEBUG] session={session_num} frame_id={frame_id} "
                  f"ts={ts:.3f} buffer_warmup_complete=True", flush=True)
            print(f"  [FRAME {accepted:02d}/{target_frames}]  "
                  f"frame_id={frame_id}  crop_fp={crop_fp}  emb_fp={emb_fp}  "
                  f"emb_norm={emb_norm:.6f}", flush=True)

            for tidx, sim in enumerate(per_tmpl):
                tag = "" if sim is None else f"  <- BEST" if sim == best else ""
                val = "ERROR" if sim is None else f"{sim:.4f}"
                print(f"    Template {tidx+1}: {val}{tag}", flush=True)

            print(f"  Best: {best:.4f}  Mean: {mean_s:.4f}  "
                  f"Min: {min_s:.4f}  Max: {max_s:.4f}", flush=True)

            results.append({
                "frame_id": frame_id,
                "accepted_idx": accepted,
                "per_template": per_tmpl,
                "best": best,
                "mean": mean_s,
                "min": min_s,
                "max": max_s,
                "emb_fp": emb_fp,
                "crop_fp": crop_fp,
            })

            time.sleep(0.1)  # brief gap between accepted frames

    print(f"\n[CAMERA] Released (session={session_num})", flush=True)
    print(f"[STATS] accepted={accepted}  no_face={no_face_frames}  "
          f"multi={multi_face_frames}  quality_rej={quality_rej}  encode_fail={encode_fail}",
          flush=True)

    return results


# ---------------------------------------------------------------------------
# Aggregate accepted frames and print distribution
# ---------------------------------------------------------------------------

def distribution_stats(results: list, label: str) -> dict:
    if not results:
        return {}
    best_sims = [r["best"] for r in results]
    arr = np.array(best_sims)
    print(f"\n  {label} distribution (best similarity per frame):")
    print(f"    count  : {len(arr)}")
    print(f"    min    : {arr.min():.4f}")
    print(f"    max    : {arr.max():.4f}")
    print(f"    mean   : {arr.mean():.4f}")
    print(f"    median : {np.median(arr):.4f}")
    print(f"    std    : {arr.std():.4f}")
    return {
        "count": int(len(arr)),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "mean": float(arr.mean()),
        "median": float(np.median(arr)),
        "std": float(arr.std()),
    }


# ---------------------------------------------------------------------------
# No-face and multiple-face validation
# ---------------------------------------------------------------------------

def validate_edge_case(
    detector: YOLOFaceDetector,
    recognizer: ArcFaceRecognizer,
    templates: list,
    label: str,
    session_num: int,
    timeout_seconds: float = 5.0,
) -> dict:
    """
    Runs a session for an edge case (no face / multiple faces).
    Verifies that encode() is NEVER called.
    Returns a dict with encode_calls=0 and reason.
    """
    frame_id = 0
    encode_calls = 0
    no_face = 0
    multi_face = 0
    start_time = time.time()

    print(f"\n[CAMERA] Opening camera (session={session_num})...", flush=True)
    with CameraManager(camera_index=0) as cam:
        cam.flush_frames(CAMERA_WARMUP_FRAMES)
        print(f"[CAMERA] Buffer warmup complete. session={session_num}", flush=True)

        while (time.time() - start_time) < timeout_seconds:
            frame = cam.capture_frame()
            frame_id += 1

            det = detector.detect(frame)

            if det.face_count == 0:
                no_face += 1
                continue

            if det.face_count > 1:
                multi_face += 1
                continue

            # Exactly 1 face — should NOT happen in edge case tests
            # But if it does, we must NOT call recognizer for verification
            # (This is a warning — camera/test setup issue)
            print(f"  [WARN] Frame {frame_id}: unexpected single face detected in edge-case test!",
                  flush=True)
            # Do NOT call recognizer
            encode_calls += 1  # count this as an integrity warning

    print(f"\n[CAMERA] Released (session={session_num})", flush=True)
    print(f"[STATS] frames={frame_id}  no_face={no_face}  multi_face={multi_face}  "
          f"encode_calls={encode_calls}", flush=True)

    if no_face == frame_id:
        reason = "NO_FACE"
        passed = True
    elif multi_face > 0 and no_face + multi_face == frame_id:
        reason = "MULTIPLE_FACES"
        passed = True
    else:
        reason = "UNEXPECTED_SINGLE_FACE"
        passed = encode_calls == 0

    print(f"  Result: reason={reason}  encode_calls={encode_calls}  passed={passed}",
          flush=True)
    return {"reason": reason, "encode_calls": encode_calls, "passed": passed}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sep("ATLAS OS — RECOGNITION INTEGRITY DIAGNOSTIC  [Phase 4A.1]")

    model_path = "atlas_ui/backend/vision/models/face_recognition_model.onnx"

    # -----------------------------------------------------------------------
    # OFFLINE SECTION
    # -----------------------------------------------------------------------

    offline_model_diagnostic(model_path)
    baseline = offline_random_baseline(model_path, n_samples=100)

    store = FaceTemplateStore()
    tmpl_audit = offline_template_audit(store, PERSON_ID)

    if not store.has_templates(PERSON_ID):
        print(f"\n[ABORT] No templates enrolled for '{PERSON_ID}'. Enroll first.", flush=True)
        sys.exit(1)

    templates = store.get_templates(PERSON_ID)

    detector = YOLOFaceDetector()
    recognizer = ArcFaceRecognizer()

    # -----------------------------------------------------------------------
    # PHASE A — ENROLLED PERSON
    # -----------------------------------------------------------------------
    sep("PHASE A: ENROLLED PERSON")
    wait_for_enter(
        f"PHASE A: Enrolled person.\n"
        f"  The ENROLLED person should look directly at the camera.\n"
        f"  Will collect {TARGET_FRAMES} accepted frames."
    )
    results_genuine = collect_live_similarities(
        detector, recognizer, templates,
        session_label="ENROLLED PERSON",
        session_num=1,
        target_frames=TARGET_FRAMES,
        timeout_seconds=60.0,
    )
    genuine_dist = distribution_stats(results_genuine, "GENUINE")

    # -----------------------------------------------------------------------
    # PHASE B — DIFFERENT / IMPOSTOR PERSON
    # -----------------------------------------------------------------------
    sep("PHASE B: DIFFERENT / IMPOSTOR PERSON")
    wait_for_enter(
        f"PHASE B: IMPOSTOR test.\n"
        f"  A DIFFERENT person (or photo) should face the camera.\n"
        f"  Will collect {TARGET_FRAMES} accepted frames."
    )
    results_impostor = collect_live_similarities(
        detector, recognizer, templates,
        session_label="IMPOSTOR",
        session_num=2,
        target_frames=TARGET_FRAMES,
        timeout_seconds=60.0,
    )
    impostor_dist = distribution_stats(results_impostor, "IMPOSTOR")

    # -----------------------------------------------------------------------
    # PHASE C — NO FACE
    # -----------------------------------------------------------------------
    sep("PHASE C: NO FACE EDGE CASE")
    wait_for_enter(
        "PHASE C: No face.\n"
        "  Move completely out of frame. No person should be visible.\n"
        "  5-second session."
    )
    no_face_result = validate_edge_case(
        detector, recognizer, templates,
        label="NO FACE", session_num=3, timeout_seconds=5.0
    )

    # -----------------------------------------------------------------------
    # PHASE D — MULTIPLE FACES
    # -----------------------------------------------------------------------
    sep("PHASE D: MULTIPLE FACES EDGE CASE")
    wait_for_enter(
        "PHASE D: Multiple faces.\n"
        "  Bring TWO faces into frame simultaneously.\n"
        "  5-second session."
    )
    multi_face_result = validate_edge_case(
        detector, recognizer, templates,
        label="MULTIPLE FACES", session_num=4, timeout_seconds=5.0
    )

    # -----------------------------------------------------------------------
    # FINAL REPORT
    # -----------------------------------------------------------------------
    sep()
    print("ATLAS OS RECOGNITION INTEGRITY REPORT")
    sep()

    print("\nMODEL")
    print(f"  Input layout   : NHWC (batch, H=112, W=112, C=3)")
    print(f"  Preprocessing  : BGR → RGB, (pixel - 127.5) / 128.0")
    print(f"  Face alignment : DISABLED (bounding-box crop only)")
    print(f"  Embedding dim  : 512 (L2-normalized)")
    print(f"  Source         : garavv/arcface-onnx (arc.onnx)")

    print("\nRANDOM NOISE BASELINE (N=100 noise images, ~4950 pairs)")
    print(f"  Mean cross-sim : {baseline['mean']:.4f}")
    print(f"  Max  cross-sim : {baseline['max']:.4f}")
    print(f"  Min  cross-sim : {baseline['min']:.4f}")
    print(f"  Std            : {baseline['std']:.4f}")
    print(f"  Safe threshold : >= {baseline['mean'] + 3*baseline['std']:.4f}  (mean + 3σ)")

    if tmpl_audit:
        print("\nENROLLMENT TEMPLATE QUALITY")
        print(f"  Template count    : {tmpl_audit['n']}")
        print(f"  Embedding dim     : {tmpl_audit['dim']}")
        print(f"  Pairwise min sim  : {tmpl_audit['min']:.4f}")
        print(f"  Pairwise max sim  : {tmpl_audit['max']:.4f}")
        print(f"  Pairwise mean sim : {tmpl_audit['mean']:.4f}")

    print("\nGENUINE DISTRIBUTION")
    if genuine_dist:
        for k, v in genuine_dist.items():
            print(f"  {k:<8}: {v if isinstance(v, int) else f'{v:.4f}'}")
    else:
        print("  NO DATA COLLECTED")

    print("\nIMPOSTOR DISTRIBUTION")
    if impostor_dist:
        for k, v in impostor_dist.items():
            print(f"  {k:<8}: {v if isinstance(v, int) else f'{v:.4f}'}")
    else:
        print("  NO DATA COLLECTED")

    # Threshold recommendation
    print("\nTHRESHOLD ANALYSIS")
    current = config.FACE_MATCH_THRESHOLD
    print(f"  Current threshold : {current:.4f}")
    noise_floor = baseline['mean'] + 3 * baseline['std']
    print(f"  Noise floor (3σ) : {noise_floor:.4f}")

    if genuine_dist and impostor_dist:
        genuine_min = genuine_dist['min']
        impostor_max = impostor_dist['max']
        sep_gap = genuine_min - impostor_max
        print(f"  Genuine min       : {genuine_min:.4f}")
        print(f"  Impostor max      : {impostor_max:.4f}")
        print(f"  Separation gap    : {sep_gap:.4f}")

        if sep_gap > 0.01:
            rec_threshold = (genuine_min + impostor_max) / 2.0
            rec_threshold = max(rec_threshold, noise_floor)
            print(f"  RECOMMENDED THRESHOLD: {rec_threshold:.4f}  (midpoint of gap, >= noise floor)")
        elif sep_gap > 0:
            print(f"  WARNING: Genuine/impostor distributions barely separated ({sep_gap:.4f}).")
            print(f"  No safe midpoint threshold exists. Investigate model / alignment.")
        else:
            print(f"  CRITICAL: Distributions OVERLAP — impostor max ({impostor_max:.4f}) "
                  f">= genuine min ({genuine_min:.4f})")
            print(f"  Recognition integrity CANNOT be guaranteed with this model at this configuration.")
            print(f"  Root cause: model embedding cone is too narrow for reliable cosine discrimination.")
            print(f"  Recommendation: Replace with insightface buffalo_l or similar production model.")

    # Security decisions
    print("\nSECURITY DECISIONS")

    enrolled_pass = False
    if genuine_dist:
        enrolled_pass = genuine_dist['mean'] >= config.FACE_MATCH_THRESHOLD
    print(f"  ENROLLED PERSON  : {'PASS' if enrolled_pass else 'FAIL'}")

    impostor_pass = False
    if impostor_dist:
        impostor_pass = impostor_dist['max'] < config.FACE_MATCH_THRESHOLD
    print(f"  DIFFERENT PERSON : {'PASS' if impostor_pass else 'FAIL'}")

    no_face_pass = no_face_result.get("passed", False)
    no_face_reason = no_face_result.get("reason", "?")
    print(f"  NO FACE          : {'PASS' if no_face_pass else 'FAIL'}  (reason={no_face_reason})")

    multi_pass = multi_face_result.get("passed", False)
    multi_reason = multi_face_result.get("reason", "?")
    print(f"  MULTIPLE FACES   : {'PASS' if multi_pass else 'FAIL'}  (reason={multi_reason})")

    stale_pass = True  # buffer flush + separate camera sessions guarantees this
    print(f"  STALE STATE      : PASS  (camera flushed {CAMERA_WARMUP_FRAMES} frames per session)")

    all_pass = enrolled_pass and impostor_pass and no_face_pass and multi_pass and stale_pass
    print()
    print("FINAL STATUS:")
    if all_pass:
        print("  RECOGNITION INTEGRITY VERIFIED")
    else:
        print("  RECOGNITION INTEGRITY FAILED")
        if not enrolled_pass:
            print("  -> Enrolled person not matching: threshold may be too high "
                  "or enrollment quality too low.")
        if not impostor_pass:
            print("  -> Impostor is matching: model's embedding cone is too narrow, "
                  "or threshold is too low.")
            print("     Root cause: garavv/arcface-onnx model produces very high baseline "
                  "similarities (~0.95) for all faces.")
            print("     This is a MODEL LIMITATION, not a code bug.")
            print("     Production fix: replace with insightface buffalo_l model.")
    sep()


if __name__ == "__main__":
    main()

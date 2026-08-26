"""
One-shot forensic diagnostic — no side effects, nothing written.
Runs via: python atlas_ui/backend/vision/_forensic_scratch.py
"""
import onnxruntime as ort
import numpy as np
import json
import hashlib

MODEL = "atlas_ui/backend/vision/models/face_recognition_model.onnx"
STORE = "atlas_ui/backend/data/face_templates.json"
PERSON = "ATLAS-P-88888888"

print("=" * 60)
print("ONNX MODEL FORENSICS")
print("=" * 60)

sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
print("Available providers:", ort.get_available_providers())
print()

for inp in sess.get_inputs():
    print(f"INPUT   name={inp.name!r}  shape={inp.shape}  dtype={inp.type}")
for out in sess.get_outputs():
    print(f"OUTPUT  name={out.name!r}  shape={out.shape}  dtype={out.type}")

# Black-image dummy
dummy_black = np.full((1, 112, 112, 3), 127.5, dtype=np.float32)
norm_black = (dummy_black - 127.5) / 128.0
e_black = sess.run(None, {"input_1": norm_black})[0][0]
print(f"\nBlack image raw norm:  {np.linalg.norm(e_black):.4f}")
print(f"Black image all finite:{np.isfinite(e_black).all()}")

# Determinism test
rng = np.random.default_rng(42)
dummy_a = rng.integers(0, 256, (1, 112, 112, 3)).astype(np.float32)
norm_a = (dummy_a - 127.5) / 128.0
e_a1 = sess.run(None, {"input_1": norm_a})[0][0]
e_a2 = sess.run(None, {"input_1": norm_a})[0][0]
print(f"Deterministic:         {np.allclose(e_a1, e_a2)}")

e_a1n = e_a1 / np.linalg.norm(e_a1)
e_a2n = e_a2 / np.linalg.norm(e_a2)
print(f"Self-similarity (norm):{np.dot(e_a1n, e_a2n):.6f}  (expect ~1.0)")

dummy_b = rng.integers(0, 256, (1, 112, 112, 3)).astype(np.float32)
norm_b = (dummy_b - 127.5) / 128.0
e_b = sess.run(None, {"input_1": norm_b})[0][0]
e_bn = e_b / np.linalg.norm(e_b)
print(f"Random cross-sim:      {np.dot(e_a1n, e_bn):.6f}  (random noise, expect low ~0.0)")

# BGR vs RGB test
dummy_c_bgr = rng.integers(0, 256, (1, 112, 112, 3)).astype(np.float32)
dummy_c_rgb = dummy_c_bgr[:, :, :, ::-1].copy()
norm_bgr = (dummy_c_bgr - 127.5) / 128.0
norm_rgb = (dummy_c_rgb - 127.5) / 128.0
e_bgr = sess.run(None, {"input_1": norm_bgr})[0][0]
e_rgb = sess.run(None, {"input_1": norm_rgb})[0][0]
e_bgr_n = e_bgr / np.linalg.norm(e_bgr)
e_rgb_n = e_rgb / np.linalg.norm(e_rgb)
print(f"\nBGR vs RGB self-cross: {np.dot(e_bgr_n, e_rgb_n):.6f}")
print("  -> If near 1.0: BGR/RGB order does NOT significantly affect this model")
print("  -> If << 1.0:   BGR/RGB order matters")

print()
print("=" * 60)
print("TEMPLATE STORE AUDIT")
print("=" * 60)

with open(STORE) as f:
    data = json.load(f)

rec = data["people"].get(PERSON)
if rec is None:
    print("NOT ENROLLED")
else:
    templates = rec["templates"]
    dim = rec["embedding_dimension"]
    count = len(templates)
    enrolled_at = rec.get("enrolled_at", "unknown")
    print(f"person_id   : {PERSON}")
    print(f"count       : {count}")
    print(f"dim         : {dim}")
    print(f"enrolled_at : {enrolled_at}")
    print()

    arrs = [np.array(t, dtype=np.float64) for t in templates]
    fps = [hashlib.md5(a.astype(np.float32).tobytes()).hexdigest()[:12] for a in arrs]

    for i, (arr, fp) in enumerate(zip(arrs, fps)):
        norm = float(np.linalg.norm(arr))
        print(f"  T{i+1}: fp={fp}  norm={norm:.6f}  mean={np.mean(arr):.6f}  std={np.std(arr):.6f}")

    unique_fps = set(fps)
    print(f"\nUnique fingerprints: {len(unique_fps)} / {count}")
    if len(unique_fps) < count:
        print("CRITICAL: DUPLICATE TEMPLATES DETECTED")

    n = len(arrs)
    sims = [[float(np.dot(arrs[i], arrs[j])) for j in range(n)] for i in range(n)]
    print("\nPairwise cosine similarity matrix (dot product of stored vectors):")
    print("      " + "".join(f"    T{j+1}" for j in range(n)))
    for i in range(n):
        row = f"  T{i+1}  " + "".join(f"{sims[i][j]:6.4f}" for j in range(n))
        print(row)

    off = [sims[i][j] for i in range(n) for j in range(n) if i != j]
    min_off = min(off)
    max_off = max(off)
    mean_off = sum(off) / len(off)
    print(f"\nOff-diagonal: min={min_off:.4f}  max={max_off:.4f}  mean={mean_off:.4f}")

    if max_off > 0.999:
        print("WARNING: ENROLLMENT SAMPLES HAVE EXTREMELY LOW VARIATION (max > 0.999)")
        print("         Likely cause: frames captured too quickly (same pose/expression)")
    elif max_off > 0.98:
        print("NOTE: High intra-template similarity (max > 0.98)")
        print("      May indicate limited pose variation; consider re-enrolling with varied expressions")
    elif min_off < 0.80:
        print("NOTE: Some template pairs have low similarity (< 0.80) — check for mis-captured frames")
    else:
        print("Template cluster quality: GOOD")

import json
import os
import pytest

from atlas_ui.backend.vision.recognition_validation import (
    ValidationSample,
    ScenarioResult,
    ValidationReport,
    calculate_statistics,
    calibrate_threshold,
    generate_report_text,
    save_report_json
)

# ------------------------------------------------------------------
# Test Statistics Calculation
# ------------------------------------------------------------------

def test_calculate_statistics_empty():
    res = calculate_statistics([])
    assert res.scenario == "UNKNOWN"
    assert res.total_attempts == 0
    assert res.accepted_samples == 0
    assert res.rejected_samples == 0


def test_calculate_statistics_all_rejected():
    s1 = ValidationSample("TEST", 1, 0.0, False, "NO_FACE")
    s2 = ValidationSample("TEST", 2, 0.0, False, "MULTIPLE_FACES")
    
    res = calculate_statistics([s1, s2])
    assert res.scenario == "TEST"
    assert res.total_attempts == 2
    assert res.accepted_samples == 0
    assert res.rejected_samples == 2
    assert res.reason_counts == {"NO_FACE": 1, "MULTIPLE_FACES": 1}
    assert res.mean_similarity == 0.0


def test_calculate_statistics_accepted():
    samples = [
        ValidationSample("TEST", 1, 0.2, True, "ACCEPTED"),
        ValidationSample("TEST", 2, 0.4, True, "ACCEPTED"),
        ValidationSample("TEST", 3, 0.6, True, "ACCEPTED"),
        ValidationSample("TEST", 4, 0.0, False, "NO_FACE")
    ]
    
    res = calculate_statistics(samples)
    assert res.scenario == "TEST"
    assert res.total_attempts == 4
    assert res.accepted_samples == 3
    assert res.rejected_samples == 1
    
    # scores: 0.2, 0.4, 0.6
    assert res.min_similarity == 0.2
    assert res.max_similarity == 0.6
    assert pytest.approx(res.mean_similarity) == 0.4
    assert res.median_similarity == 0.4
    
    # variance = ((0.2-0.4)^2 + (0.4-0.4)^2 + (0.6-0.4)^2)/3 = (0.04 + 0 + 0.04)/3 = 0.08/3 = 0.02666...
    # std_dev = sqrt(0.02666...) ~ 0.1633
    assert pytest.approx(res.standard_deviation, 0.001) == 0.163299
    

# ------------------------------------------------------------------
# Test Threshold Calibration
# ------------------------------------------------------------------

def test_calibrate_threshold_insufficient_data():
    res = calibrate_threshold([], [0.1, 0.2])
    assert res["status"] == "FAIL"
    assert res["recommended_threshold"] is None
    
    res2 = calibrate_threshold([0.8, 0.9], [])
    assert res2["status"] == "FAIL"


def test_calibrate_threshold_clean_separation():
    # Impostors all below 0.3, Genuine all above 0.7
    impostors = [0.05, 0.1, 0.2, 0.25]
    genuine = [0.75, 0.8, 0.9, 0.95]
    
    res = calibrate_threshold(genuine, impostors)
    assert res["status"] == "PASS"
    assert res["far"] == 0.0
    assert res["frr"] == 0.0
    # Any threshold between 0.25 and 0.75 satisfies FAR=0 and FRR=0.
    # The algorithm returns the middle of these.
    # Candidates: 0.26 to 0.75 (50 items).
    # Middle is roughly (0.26 + 0.75)/2 = 0.505.
    assert 0.25 < res["recommended_threshold"] <= 0.75


def test_calibrate_threshold_overlap():
    # Impostors reach 0.6, Genuine drop to 0.4.
    impostors = [0.1, 0.3, 0.5, 0.6]
    genuine = [0.4, 0.7, 0.8, 0.9]
    
    res = calibrate_threshold(genuine, impostors)
    # The algorithm prioritizes FAR=0, so it must pick threshold > 0.6 (e.g. 0.601)
    # At this threshold, the genuine score 0.4 is falsely rejected.
    # So FRR should be 1/4 = 0.25
    assert res["status"] == "WARNING"
    assert res["recommended_threshold"] > 0.6
    assert res["far"] == 0.0
    assert res["frr"] >= 0.25


# ------------------------------------------------------------------
# Test Report Generation
# ------------------------------------------------------------------

def test_generate_report_text():
    dummy_res = ScenarioResult(
        scenario="TEST", total_attempts=5, accepted_samples=5, rejected_samples=0,
        min_similarity=0.8, max_similarity=0.9, mean_similarity=0.85,
        median_similarity=0.85, standard_deviation=0.01, reason_counts={"ACCEPTED": 5}
    )
    
    report = ValidationReport(
        person_id="U-123", model_name="test_model", embedding_dimension=512,
        enrolled_template_count=5, genuine_result=dummy_res, impostor_result=dummy_res,
        no_face_result=ScenarioResult("NO_FACE", 5, 0, 5),
        multiple_faces_result=ScenarioResult("MULTIPLE", 5, 0, 5),
        pose_results={"front": dummy_res}, lighting_results={"normal": dummy_res},
        recommended_threshold=0.5, threshold_method="Test method", overall_status="PASS",
        far_at_recommended=0.0, frr_at_recommended=0.0, eer_approximation=0.0
    )
    
    txt = generate_report_text(report, 0.35)
    
    assert "ATLAS OS REAL-WORLD BIOMETRIC VALIDATION REPORT" in txt
    assert "U-123" in txt
    assert "test_model" in txt
    assert "AUTHORIZED PERSON" in txt
    assert "NO FACE" in txt
    assert "MULTIPLE FACES" in txt
    assert "Result: PASS" in txt
    assert "Calibrated threshold:         0.5000" in txt
    assert "FINAL SECURITY ASSESSMENT" in txt
    assert "PASS" in txt


def test_save_report_json(tmp_path):
    filepath = os.path.join(tmp_path, "report.json")
    
    dummy_res = ScenarioResult(
        scenario="TEST", total_attempts=5, accepted_samples=5, rejected_samples=0,
        min_similarity=0.8, max_similarity=0.9, mean_similarity=0.85,
        median_similarity=0.85, standard_deviation=0.01, reason_counts={"ACCEPTED": 5}
    )
    
    report = ValidationReport(
        person_id="U-123", model_name="test_model", embedding_dimension=512,
        enrolled_template_count=5, genuine_result=dummy_res, impostor_result=dummy_res,
        no_face_result=ScenarioResult("NO_FACE", 5, 0, 5),
        multiple_faces_result=ScenarioResult("MULTIPLE", 5, 0, 5),
        pose_results={"front": dummy_res}, lighting_results={"normal": dummy_res},
        recommended_threshold=0.5, threshold_method="Test method", overall_status="PASS",
        far_at_recommended=0.0, frr_at_recommended=0.0, eer_approximation=0.0
    )
    
    save_report_json(report, filepath)
    
    assert os.path.exists(filepath)
    with open(filepath, "r") as f:
        data = json.load(f)
        
    assert data["person_id"] == "U-123"
    assert data["recommended_threshold"] == 0.5
    assert data["scenarios"]["genuine"]["mean_similarity"] == 0.85
    assert "poses" in data["scenarios"]
    assert "front" in data["scenarios"]["poses"]
    
    # Samples list shouldn't be serialized to avoid bloated JSON
    assert "samples" not in data["scenarios"]["genuine"]

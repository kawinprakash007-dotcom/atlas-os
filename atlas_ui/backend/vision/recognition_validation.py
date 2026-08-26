import json
import math
import os
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any


@dataclass
class ValidationSample:
    scenario: str
    sample_number: int
    similarity: float
    accepted: bool
    reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class ScenarioResult:
    scenario: str
    total_attempts: int
    accepted_samples: int
    rejected_samples: int
    min_similarity: float = 0.0
    max_similarity: float = 0.0
    mean_similarity: float = 0.0
    median_similarity: float = 0.0
    standard_deviation: float = 0.0
    reason_counts: Dict[str, int] = field(default_factory=dict)
    samples: List[ValidationSample] = field(default_factory=list)


@dataclass
class ValidationReport:
    person_id: str
    model_name: str
    embedding_dimension: int
    enrolled_template_count: int
    
    genuine_result: ScenarioResult
    impostor_result: ScenarioResult
    no_face_result: ScenarioResult
    multiple_faces_result: ScenarioResult
    pose_results: Dict[str, ScenarioResult]
    lighting_results: Dict[str, ScenarioResult]
    
    recommended_threshold: Optional[float] = None
    threshold_method: Optional[str] = None
    overall_status: str = "PENDING"
    
    far_at_recommended: float = 1.0
    frr_at_recommended: float = 1.0
    eer_approximation: float = 1.0


def calculate_statistics(samples: List[ValidationSample]) -> ScenarioResult:
    """Calculates min, max, mean, median, std_dev from a list of validation samples."""
    if not samples:
        return ScenarioResult(
            scenario="UNKNOWN", total_attempts=0, accepted_samples=0, rejected_samples=0
        )
    
    scenario_name = samples[0].scenario
    total = len(samples)
    
    accepted_samples = [s for s in samples if s.accepted]
    rejected = total - len(accepted_samples)
    
    reason_counts: Dict[str, int] = {}
    for s in samples:
        reason_counts[s.reason] = reason_counts.get(s.reason, 0) + 1
        
    scores = [s.similarity for s in accepted_samples if s.similarity is not None]
    
    if not scores:
        return ScenarioResult(
            scenario=scenario_name,
            total_attempts=total,
            accepted_samples=0,
            rejected_samples=rejected,
            reason_counts=reason_counts,
            samples=samples
        )
        
    scores.sort()
    min_score = scores[0]
    max_score = scores[-1]
    mean_score = sum(scores) / len(scores)
    
    mid = len(scores) // 2
    if len(scores) % 2 == 0:
        median_score = (scores[mid - 1] + scores[mid]) / 2.0
    else:
        median_score = scores[mid]
        
    variance = sum((x - mean_score) ** 2 for x in scores) / len(scores)
    std_dev = math.sqrt(variance)
    
    return ScenarioResult(
        scenario=scenario_name,
        total_attempts=total,
        accepted_samples=len(accepted_samples),
        rejected_samples=rejected,
        min_similarity=min_score,
        max_similarity=max_score,
        mean_similarity=mean_score,
        median_similarity=median_score,
        standard_deviation=std_dev,
        reason_counts=reason_counts,
        samples=samples
    )


def calibrate_threshold(genuine_scores: List[float], impostor_scores: List[float]) -> dict:
    """
    Evaluates candidate thresholds across genuine and impostor scores.
    Returns recommended threshold, FAR, FRR, EER, and method string.
    """
    if not genuine_scores or not impostor_scores:
        return {
            "recommended_threshold": None,
            "far": 1.0,
            "frr": 1.0,
            "eer": 1.0,
            "method": "INSUFFICIENT DATA",
            "status": "FAIL"
        }
        
    # Check for complete overlap
    if min(genuine_scores) <= max(impostor_scores):
        overlap = True
    else:
        overlap = False
        
    # We will check thresholds from 0.00 to 1.00 in increments of 0.01
    candidates = [i / 1000.0 for i in range(1001)]
    
    best_eer_diff = 1.0
    eer_approx = 1.0
    
    # We want a conservative threshold where FAR = 0.0 while minimizing FRR
    safe_candidates = []
    
    for t in candidates:
        # FAR = False Acceptance Rate = % of impostors >= threshold
        false_accepts = sum(1 for s in impostor_scores if s >= t)
        far = false_accepts / len(impostor_scores)
        
        # FRR = False Rejection Rate = % of genuine < threshold
        false_rejects = sum(1 for s in genuine_scores if s < t)
        frr = false_rejects / len(genuine_scores)
        
        diff = abs(far - frr)
        if diff < best_eer_diff:
            best_eer_diff = diff
            eer_approx = (far + frr) / 2.0
            
        if far == 0.0:
            safe_candidates.append((t, frr))
            
    if not safe_candidates:
        return {
            "recommended_threshold": None,
            "far": 1.0,
            "frr": 1.0,
            "eer": eer_approx,
            "method": "NO SAFE THRESHOLD FOUND (FAR > 0.0 FOR ALL)",
            "status": "FAIL"
        }
        
    # Find the threshold with FAR=0 and the lowest FRR
    # If multiple have the same lowest FRR, pick the middle one to maximize margin
    safe_candidates.sort(key=lambda x: (x[1], x[0]))
    lowest_frr = safe_candidates[0][1]
    
    best_options = [c[0] for c in safe_candidates if c[1] == lowest_frr]
    recommended_threshold = best_options[len(best_options) // 2]
    
    status = "WARNING" if overlap else "PASS"
    method = f"Lowest threshold satisfying FAR = 0.0000 while minimizing FRR (FRR={lowest_frr:.4f})"
    
    return {
        "recommended_threshold": recommended_threshold,
        "far": 0.0,
        "frr": lowest_frr,
        "eer": eer_approx,
        "method": method,
        "status": status
    }


def generate_report_text(report: ValidationReport, current_production_threshold: float) -> str:
    """Generates the formatted text report from the ValidationReport object."""
    
    lines = []
    lines.append("====================================================")
    lines.append("ATLAS OS REAL-WORLD BIOMETRIC VALIDATION REPORT")
    lines.append("====================================================")
    lines.append("")
    lines.append(f"Person ID:           {report.person_id}")
    lines.append(f"Model:               {report.model_name}")
    lines.append(f"Embedding dimension: {report.embedding_dimension}")
    lines.append(f"Template count:      {report.enrolled_template_count}")
    lines.append("")
    
    def format_scenario(name: str, res: ScenarioResult):
        lines.append("-" * 52)
        lines.append(name)
        lines.append("-" * 52)
        lines.append(f"Total Attempts:   {res.total_attempts}")
        lines.append(f"Accepted Samples: {res.accepted_samples}")
        lines.append(f"Rejected Samples: {res.rejected_samples}")
        if res.accepted_samples > 0:
            lines.append(f"Minimum:          {res.min_similarity:.4f}")
            lines.append(f"Maximum:          {res.max_similarity:.4f}")
            lines.append(f"Mean:             {res.mean_similarity:.4f}")
            lines.append(f"Median:           {res.median_similarity:.4f}")
            lines.append(f"Std Dev:          {res.standard_deviation:.4f}")
        lines.append("")
        
    format_scenario("AUTHORIZED PERSON", report.genuine_result)
    format_scenario("IMPOSTOR PERSON", report.impostor_result)
    
    lines.append("-" * 52)
    lines.append("NO FACE")
    lines.append("-" * 52)
    pass_no_face = (report.no_face_result.accepted_samples == 0)
    lines.append(f"Result: {'PASS' if pass_no_face else 'FAIL'}")
    lines.append("")
    
    lines.append("-" * 52)
    lines.append("MULTIPLE FACES")
    lines.append("-" * 52)
    pass_mult = (report.multiple_faces_result.accepted_samples == 0)
    lines.append(f"Result: {'PASS' if pass_mult else 'FAIL'}")
    lines.append("")
    
    lines.append("-" * 52)
    lines.append("POSE ROBUSTNESS")
    lines.append("-" * 52)
    for pose, res in report.pose_results.items():
        if res.accepted_samples > 0:
            lines.append(f"{pose.upper():<10} mean={res.mean_similarity:.4f}  (n={res.accepted_samples})")
        else:
            lines.append(f"{pose.upper():<10} FAILED TO COLLECT")
    lines.append("")
    
    lines.append("-" * 52)
    lines.append("LIGHTING ROBUSTNESS")
    lines.append("-" * 52)
    for light, res in report.lighting_results.items():
        if res.accepted_samples > 0:
            lines.append(f"{light.upper():<12} mean={res.mean_similarity:.4f}  (n={res.accepted_samples})")
        else:
            lines.append(f"{light.upper():<12} FAILED TO COLLECT")
    lines.append("")
    
    lines.append("-" * 52)
    lines.append("THRESHOLD ANALYSIS")
    lines.append("-" * 52)
    lines.append(f"Current production threshold: {current_production_threshold:.4f}")
    if report.recommended_threshold is not None:
        lines.append(f"Calibrated threshold:         {report.recommended_threshold:.4f}")
        lines.append(f"False Acceptance Rate:        {report.far_at_recommended:.4f}")
        lines.append(f"False Rejection Rate:         {report.frr_at_recommended:.4f}")
        lines.append(f"EER approximation:            {report.eer_approximation:.4f}")
        lines.append(f"Threshold method:             {report.threshold_method}")
    else:
        lines.append("Calibrated threshold:         FAILED TO CALIBRATE")
        lines.append(f"Threshold method:             {report.threshold_method}")
    lines.append("")
    
    lines.append("-" * 52)
    lines.append("FINAL SECURITY ASSESSMENT")
    lines.append("-" * 52)
    lines.append(report.overall_status)
    lines.append("====================================================")
    
    return "\n".join(lines)


def save_report_json(report: ValidationReport, filepath: str):
    """Saves the ValidationReport as a JSON file, discarding raw samples."""
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    
    def serialize_scenario(res: ScenarioResult) -> dict:
        return {
            "scenario": res.scenario,
            "total_attempts": res.total_attempts,
            "accepted_samples": res.accepted_samples,
            "rejected_samples": res.rejected_samples,
            "min_similarity": res.min_similarity,
            "max_similarity": res.max_similarity,
            "mean_similarity": res.mean_similarity,
            "median_similarity": res.median_similarity,
            "standard_deviation": res.standard_deviation,
            "reason_counts": res.reason_counts
        }
        
    data = {
        "person_id": report.person_id,
        "model_name": report.model_name,
        "embedding_dimension": report.embedding_dimension,
        "enrolled_template_count": report.enrolled_template_count,
        "overall_status": report.overall_status,
        "recommended_threshold": report.recommended_threshold,
        "far_at_recommended": report.far_at_recommended,
        "frr_at_recommended": report.frr_at_recommended,
        "eer_approximation": report.eer_approximation,
        "threshold_method": report.threshold_method,
        "scenarios": {
            "genuine": serialize_scenario(report.genuine_result),
            "impostor": serialize_scenario(report.impostor_result),
            "no_face": serialize_scenario(report.no_face_result),
            "multiple_faces": serialize_scenario(report.multiple_faces_result),
            "poses": {k: serialize_scenario(v) for k, v in report.pose_results.items()},
            "lighting": {k: serialize_scenario(v) for k, v in report.lighting_results.items()}
        }
    }
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=4)

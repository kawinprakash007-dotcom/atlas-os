"""
Tests for FaceTemplateStore — v2 schema with recognizer metadata.
"""
import pytest
import os
import json

from atlas_ui.backend.vision.face_template_store import (
    FaceTemplateStore, TemplateStatus, RECOGNIZER_ID
)


def test_face_template_store_lifecycle(tmp_path):
    """Full save/load/delete cycle with status checks."""
    store_file = os.path.join(tmp_path, "face_templates.json")
    store = FaceTemplateStore(store_path=store_file)

    person_id = "test-user-1"
    templates = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    assert store.has_templates(person_id) is False
    assert store.get_templates(person_id) is None
    assert store.get_template_status(person_id) == TemplateStatus.NOT_ENROLLED

    # Save with correct recognizer
    store.save_templates(person_id, templates, recognizer=RECOGNIZER_ID)
    assert store.has_templates(person_id) is True
    assert store.get_templates(person_id) == templates
    assert store.get_template_status(person_id) == TemplateStatus.ENROLLED
    assert store.list_enrolled_people() == [person_id]

    # Reload from disk — status still ENROLLED
    store2 = FaceTemplateStore(store_path=store_file)
    assert store2.has_templates(person_id) is True
    assert store2.get_templates(person_id) == templates
    assert store2.get_template_status(person_id) == TemplateStatus.ENROLLED


def test_face_template_store_overwrite_protection(tmp_path):
    """Overwrite=False raises ValueError when templates already exist."""
    store_file = os.path.join(tmp_path, "face_templates.json")
    store = FaceTemplateStore(store_path=store_file)

    person_id = "test-user-1"
    store.save_templates(person_id, [[0.1, 0.2, 0.3]], recognizer=RECOGNIZER_ID)

    with pytest.raises(ValueError, match="already exist"):
        store.save_templates(person_id, [[0.5, 0.6, 0.7]], overwrite=False)

    # Overwrite=True must succeed
    store.save_templates(person_id, [[0.5, 0.6, 0.7]], recognizer=RECOGNIZER_ID, overwrite=True)
    assert store.get_templates(person_id) == [[0.5, 0.6, 0.7]]


def test_face_template_store_dimension_inconsistency(tmp_path):
    """Templates with mismatched dimensions within one save call are rejected."""
    store_file = os.path.join(tmp_path, "face_templates.json")
    store = FaceTemplateStore(store_path=store_file)

    bad_templates = [[0.1, 0.2, 0.3], [0.4, 0.5]]
    with pytest.raises(ValueError, match="inconsistent dimension"):
        store.save_templates("test-user-1", bad_templates)


def test_face_template_store_malformed_handling(tmp_path):
    """Malformed JSON raises ValueError on load."""
    store_file = os.path.join(tmp_path, "face_templates.json")
    with open(store_file, "w") as f:
        f.write("{ malformed_json: true ")

    with pytest.raises(ValueError, match="Failed to load/parse"):
        FaceTemplateStore(store_path=store_file)


def test_face_template_store_deletion(tmp_path):
    """remove_templates returns True on success, False if missing."""
    store_file = os.path.join(tmp_path, "face_templates.json")
    store = FaceTemplateStore(store_path=store_file)

    person_id = "test-user-1"
    store.save_templates(person_id, [[0.1, 0.2, 0.3]], recognizer=RECOGNIZER_ID)

    assert store.remove_templates(person_id) is True
    assert store.has_templates(person_id) is False
    assert os.path.exists(store_file)

    # Second removal should return False
    assert store.remove_templates(person_id) is False


def test_face_template_store_legacy_template_detection(tmp_path):
    """Templates with no 'recognizer' field → LEGACY_TEMPLATE status."""
    store_file = os.path.join(tmp_path, "face_templates.json")

    # Write old-format template (no recognizer field)
    old_data = {
        "version": 1,
        "people": {
            "ATLAS-P-99999": {
                "embedding_dimension": 512,
                "enrolled_at": "2026-08-01T00:00:00Z",
                "template_count": 2,
                "templates": [[0.1] * 512, [0.2] * 512]
            }
        }
    }
    with open(store_file, "w") as f:
        json.dump(old_data, f)

    store = FaceTemplateStore(store_path=store_file)
    status = store.get_template_status("ATLAS-P-99999")
    assert status == TemplateStatus.LEGACY_TEMPLATE
    # Legacy templates must NOT be compared — but they can be read for display
    assert store.has_templates("ATLAS-P-99999") is True
    # get_recognizer returns None for legacy
    assert store.get_recognizer("ATLAS-P-99999") is None


def test_face_template_store_recognizer_mismatch(tmp_path):
    """Templates from a different recognizer → RE_ENROLLMENT_REQUIRED."""
    store_file = os.path.join(tmp_path, "face_templates.json")
    store = FaceTemplateStore(store_path=store_file)

    person_id = "test-user-mismatch"
    # Save with an old recognizer name
    store.save_templates(person_id, [[0.1, 0.2, 0.3]], recognizer="old_arcface_onnx")

    status = store.get_template_status(person_id, expected_recognizer=RECOGNIZER_ID)
    assert status == TemplateStatus.RE_ENROLLMENT_REQUIRED


def test_face_template_store_recognizer_field_persisted(tmp_path):
    """The recognizer field must be persisted to disk and reloaded."""
    store_file = os.path.join(tmp_path, "face_templates.json")
    store = FaceTemplateStore(store_path=store_file)

    person_id = "test-persist"
    store.save_templates(person_id, [[0.1, 0.2]], recognizer=RECOGNIZER_ID)

    # Check raw JSON
    with open(store_file) as f:
        data = json.load(f)

    record = data["people"][person_id]
    assert record.get("recognizer") == RECOGNIZER_ID

    # Also check via store API after reload
    store2 = FaceTemplateStore(store_path=store_file)
    assert store2.get_recognizer(person_id) == RECOGNIZER_ID

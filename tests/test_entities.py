import pytest
from atlas_core.context.entities import EntityExtractor

def test_entity_extractor_extracts_known_keys():
    extractor = EntityExtractor()
    payload = {
        "person_id": "person_001",
        "camera_id": "lab_cam",
        "unknown_key": "some_value"
    }
    
    result = extractor.extract(payload)
    
    assert "person_id" in result
    assert result["person_id"] == ["person_001"]
    
    assert "camera_id" in result
    assert result["camera_id"] == ["lab_cam"]
    
    assert "unknown_key" not in result

def test_entity_extractor_handles_missing_keys():
    extractor = EntityExtractor()
    payload = {"some_other_id": "123"}
    
    result = extractor.extract(payload)
    assert result == {}

def test_entity_extractor_handles_malformed_payload():
    extractor = EntityExtractor()
    
    # Not a dict
    assert extractor.extract(None) == {}
    assert extractor.extract("string payload") == {}
    assert extractor.extract(["list", "payload"]) == {}

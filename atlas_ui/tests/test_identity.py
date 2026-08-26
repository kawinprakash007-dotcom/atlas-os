import pytest
from atlas_ui.backend.identity.person_models import Person
from atlas_ui.backend.identity.person_registry import PersonRegistry

@pytest.fixture
def clean_registry():
    return PersonRegistry()


# 1. Create person
def test_create_person(clean_registry):
    p = clean_registry.create_person(display_name="Test User", account_id="acc_123")
    assert p.display_name == "Test User"
    assert p.account_id == "acc_123"
    assert p.status == "ACTIVE"
    assert p.face_enrollment_status == "NOT_ENROLLED"
    assert p.atlas_person_id.startswith("ATLAS-P-")
    
    # 2. Status verification
    p_retrieved = clean_registry.get_person(p.atlas_person_id)
    assert p_retrieved is not None
    assert p_retrieved.status == "ACTIVE"


# 3. Lookup person
# 4. Lookup person by account
def test_person_lookup(clean_registry):
    p = clean_registry.create_person(display_name="Lookup User", account_id="acc_lookup")
    
    # Lookup by ID
    p_by_id = clean_registry.get_person(p.atlas_person_id)
    assert p_by_id.account_id == "acc_lookup"
    
    # Lookup by account ID
    p_by_acc = clean_registry.get_person_by_account("acc_lookup")
    assert p_by_acc.atlas_person_id == p.atlas_person_id
    
    # Unknown lookups return None
    assert clean_registry.get_person("ATLAS-P-UNKNOWN") is None
    assert clean_registry.get_person_by_account("acc_unknown") is None


# 5. Duplicate account rejection
def test_duplicate_account_rejection(clean_registry):
    clean_registry.create_person(display_name="User 1", account_id="acc_dup")
    with pytest.raises(ValueError):
        clean_registry.create_person(display_name="User 2", account_id="acc_dup")


# 6. Person immutability
def test_person_immutability(clean_registry):
    p = clean_registry.create_person(display_name="Original Name", account_id="acc_immutable")
    
    # Modify returned object
    p.display_name = "Hacked Name"
    
    # Check that registry internal state is not changed
    found = clean_registry.get_person(p.atlas_person_id)
    assert found.display_name == "Original Name"

import pytest
from atlas_core.memory.identity_memory import IdentityMemory, IdentityRecord

class DummyAccount:
    def __init__(self, enabled, role="USER"):
        self.enabled = enabled
        self.role = role

class DummyPerson:
    def __init__(self, atlas_person_id, display_name, account_id, role=None):
        self.atlas_person_id = atlas_person_id
        self.display_name = display_name
        self.account_id = account_id
        self.role = role

class DummyAccountRegistry:
    def __init__(self, accounts):
        self.accounts = accounts
    def get_account(self, account_id):
        return self.accounts.get(account_id)

class DummyPersonRegistry:
    def __init__(self, people):
        self.people = people
    def list_people(self):
        return self.people

class DummyFaceTemplateStore:
    def __init__(self, statuses):
        self.statuses = statuses
    def get_template_status(self, person_id):
        from atlas_ui.backend.vision.face_template_store import TemplateStatus
        return self.statuses.get(person_id, TemplateStatus.NOT_ENROLLED)

def test_empty_identity_memory_returns_no_identities():
    # 1. Empty IdentityMemory returns no identities.
    mem = IdentityMemory()
    assert len(mem.get_all_identities()) == 0
    assert mem.get_identity("missing") is None
    assert len(mem.get_vision_registry()) == 0

def test_bootstrap_correctly_loads_seeded_admin_and_user():
    # 2. bootstrap correctly loads seeded Admin and User.
    accounts = {
        "acc1": DummyAccount(enabled=True, role="ADMIN"),
        "acc2": DummyAccount(enabled=False, role="USER")
    }
    people = [
        DummyPerson("ATLAS-P-ADMIN", "Admin User", "acc1", role="ADMIN"),
        DummyPerson("ATLAS-P-USER", "Normal User", "acc2", role="USER")
    ]
    
    from atlas_ui.backend.vision.face_template_store import TemplateStatus
    statuses = {
        "ATLAS-P-ADMIN": TemplateStatus.ENROLLED
    }
    
    acc_reg = DummyAccountRegistry(accounts)
    person_reg = DummyPersonRegistry(people)
    face_store = DummyFaceTemplateStore(statuses)
    
    mem = IdentityMemory()
    mem.bootstrap(acc_reg, person_reg, face_store)
    
    assert len(mem.get_all_identities()) == 2
    
    admin = mem.get_identity("ATLAS-P-ADMIN")
    assert admin.enabled is True
    assert admin.face_enrolled is True
    
    user = mem.get_identity("ATLAS-P-USER")
    assert user.enabled is False
    assert user.face_enrolled is False

def test_get_identity_returns_correct_identity():
    # 3. get_identity returns the correct identity.
    mem = IdentityMemory()
    mem.upsert_identity("P-1", "Test 1", "USER", True, False)
    mem.upsert_identity("P-2", "Test 2", "ADMIN", True, True)
    
    id1 = mem.get_identity("P-1")
    assert id1.display_name == "Test 1"
    
    missing = mem.get_identity("P-MISSING")
    assert missing is None

def test_vision_registry_filters():
    mem = IdentityMemory()
    mem.upsert_identity("P-DISABLED", "Disabled User", "USER", enabled=False, face_enrolled=True)
    mem.upsert_identity("P-NOFACE", "No Face User", "USER", enabled=True, face_enrolled=False)
    mem.upsert_identity("P-VALID", "Valid User", "ADMIN", enabled=True, face_enrolled=True)
    
    vision_reg = mem.get_vision_registry()
    
    # 4. disabled users are excluded
    # 5. users without face enrollment are excluded
    # 6. enabled users with face enrollment appear
    
    assert len(vision_reg) == 1
    assert vision_reg[0]["person_id"] == "P-VALID"
    assert "face_enrolled" not in vision_reg[0] # Excluded from vision dict

def test_mark_face_enrolled():
    # 7. mark_face_enrolled works.
    mem = IdentityMemory()
    mem.upsert_identity("P-1", "Test", "USER", True, False)
    
    assert mem.mark_face_enrolled("P-MISSING") is False
    assert mem.mark_face_enrolled("P-1") is True
    
    updated = mem.get_identity("P-1")
    assert updated.face_enrolled is True

def test_mark_face_removed():
    # 8. mark_face_removed works.
    mem = IdentityMemory()
    mem.upsert_identity("P-1", "Test", "USER", True, True)
    
    assert mem.mark_face_removed("P-MISSING") is False
    assert mem.mark_face_removed("P-1") is True
    
    updated = mem.get_identity("P-1")
    assert updated.face_enrolled is False

def test_remove_identity():
    # 9. remove_identity works.
    mem = IdentityMemory()
    mem.upsert_identity("P-1", "Test", "USER", True, True)
    
    assert mem.remove_identity("P-MISSING") is False
    assert mem.remove_identity("P-1") is True
    
    assert mem.get_identity("P-1") is None

def test_get_all_identities_is_safe():
    # 10. get_all_identities does not expose the mutable internal dictionary.
    mem = IdentityMemory()
    mem.upsert_identity("P-1", "Test", "USER", True, True)
    
    identities = mem.get_all_identities()
    assert len(identities) == 1
    
    # Mutating the returned list should not affect the memory cache
    identities.pop()
    
    assert len(mem.get_all_identities()) == 1
    assert mem.get_identity("P-1") is not None

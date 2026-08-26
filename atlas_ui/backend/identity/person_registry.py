import copy
import time
import secrets
from typing import Dict, List, Optional
from atlas_ui.backend.identity.person_models import Person

class PersonRegistry:
    def __init__(self, sqlite_store=None):
        # Maps atlas_person_id -> Person
        self._people: Dict[str, Person] = {}
        self._store = sqlite_store

    def _generate_id(self) -> str:
        # Loop until generating a truly unique 8-character hex token ID
        while True:
            candidate = f"ATLAS-P-{secrets.token_hex(4).upper()}"
            if candidate not in self._people:
                return candidate

    def create_person(
        self,
        display_name: str,
        account_id: Optional[str] = None,
        role: Optional[str] = None,
        status: str = "ACTIVE",
        metadata: Optional[dict] = None,
        atlas_person_id: Optional[str] = None
    ) -> Person:
        # Reject duplicate account_id linkage
        if account_id:
            for p in self._people.values():
                if p.account_id == account_id:
                    raise ValueError(f"Account ID '{account_id}' is already linked to person '{p.atlas_person_id}'.")

        if atlas_person_id is None:
            atlas_person_id = self._generate_id()
        now = time.time()
        
        # Write to SQLite first
        if self._store:
            self._store.create_person(
                person_id=atlas_person_id,
                account_id=account_id,
                display_name=display_name,
                role=role,
                face_enrollment_status="NOT_ENROLLED",
                template_count=0
            )
            
        person = Person(
            atlas_person_id=atlas_person_id,
            display_name=display_name,
            account_id=account_id,
            role=role,
            status=status,
            face_enrollment_status="NOT_ENROLLED",
            created_at=now,
            updated_at=now,
            metadata=dict(metadata) if metadata is not None else {}
        )
        self._people[atlas_person_id] = person
        return copy.deepcopy(person)

    def get_person(self, atlas_person_id: str) -> Optional[Person]:
        person = self._people.get(atlas_person_id)
        if person is None:
            return None
        return copy.deepcopy(person)

    def get_person_by_account(self, account_id: str) -> Optional[Person]:
        if not account_id:
            return None
        for person in self._people.values():
            if person.account_id == account_id:
                return copy.deepcopy(person)
        return None

    def list_people(self) -> List[Person]:
        return [copy.deepcopy(p) for p in self._people.values()]

    def update_person(self, atlas_person_id: str, **kwargs) -> Person:
        if atlas_person_id not in self._people:
            raise KeyError(f"Person ID '{atlas_person_id}' does not exist.")
        
        person = self._people[atlas_person_id]
        
        # Check duplicate account linkage if account_id is being updated
        if "account_id" in kwargs:
            new_acc = kwargs["account_id"]
            if new_acc:
                for p in self._people.values():
                    if p.atlas_person_id != atlas_person_id and p.account_id == new_acc:
                        raise ValueError(f"Account ID '{new_acc}' is already linked to person '{p.atlas_person_id}'.")

        # Determine fields for SQLite
        upd_account_id = kwargs.get("account_id", person.account_id)
        upd_display_name = kwargs.get("display_name", person.display_name)
        upd_role = kwargs.get("role", person.role)
        upd_face_status = kwargs.get("face_enrollment_status", person.face_enrollment_status)
        upd_template_count = kwargs.get("template_count", person.template_count)

        # Write to SQLite first
        if self._store:
            self._store.update_person(
                person_id=atlas_person_id,
                account_id=upd_account_id,
                display_name=upd_display_name,
                role=upd_role,
                face_enrollment_status=upd_face_status,
                template_count=upd_template_count
            )

        for k, v in kwargs.items():
            if hasattr(person, k):
                setattr(person, k, v)
        
        person.updated_at = time.time()
        return copy.deepcopy(person)

    def disable_person(self, atlas_person_id: str) -> Person:
        return self.update_person(atlas_person_id, status="DISABLED")

    def revoke_person(self, atlas_person_id: str) -> Person:
        return self.update_person(atlas_person_id, status="REVOKED", face_enrollment_status="REVOKED")

    def remove_person(self, atlas_person_id: str) -> None:
        if atlas_person_id not in self._people:
            raise KeyError(f"Person ID '{atlas_person_id}' does not exist.")
            
        if self._store:
            self._store.delete_person(atlas_person_id)
            
        self._people.pop(atlas_person_id)

import threading
from typing import Dict, List, Optional
from dataclasses import dataclass, replace
from pydantic import BaseModel

@dataclass(frozen=True)
class IdentityRecord:
    """
    Read-only identity projection.
    Does NOT contain passwords, hashes, tokens, or biometric embeddings.
    """
    person_id: str
    display_name: str
    role: str
    enabled: bool
    face_enrolled: bool

class IdentityMemory:
    """
    Synchronized cache/projection of identity state.
    Provides a read-optimized layer for ATLAS Vision and Assistant.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._cache: Dict[str, IdentityRecord] = {}
        self.on_mutation_callbacks = []

    def _trigger_mutations(self):
        for cb in self.on_mutation_callbacks:
            try:
                cb()
            except Exception as e:
                print(f"[IdentityMemory] Mutation callback error: {e}")

    def bootstrap(self, account_registry, person_registry, face_template_store) -> None:
        """
        Builds the initial in-memory identity cache from existing registries.
        """
        with self._lock:
            self._cache.clear()
            for person in person_registry.list_people():
                account = account_registry.get_account(person.account_id) if person.account_id else None
                
                # If there's no account, we default to disabled since ATLAS relies on accounts
                enabled = account.enabled if account else False
                
                # Check FaceTemplateStore for enrolled biometrics
                try:
                    tmpl_status = face_template_store.get_template_status(person.atlas_person_id)
                    from atlas_ui.backend.vision.face_template_store import TemplateStatus
                    face_enrolled = (tmpl_status == TemplateStatus.ENROLLED)
                except Exception:
                    face_enrolled = False

                record = IdentityRecord(
                    person_id=person.atlas_person_id,
                    display_name=person.display_name,
                    role=person.role or (account.role if account else "USER"),
                    enabled=enabled,
                    face_enrolled=face_enrolled
                )
                self._cache[person.atlas_person_id] = record

    def upsert_identity(self, person_id: str, display_name: str, role: str, enabled: bool, face_enrolled: bool) -> None:
        """
        Adds or completely updates an identity in the cache.
        """
        with self._lock:
            self._cache[person_id] = IdentityRecord(
                person_id=person_id,
                display_name=display_name,
                role=role,
                enabled=enabled,
                face_enrolled=face_enrolled
            )
            self._trigger_mutations()

    def get_identity(self, person_id: str) -> Optional[IdentityRecord]:
        """
        Returns a specific IdentityRecord, or None if missing.
        """
        with self._lock:
            return self._cache.get(person_id)

    def get_all_identities(self) -> List[IdentityRecord]:
        """
        Returns a safe list of all identities.
        (IdentityRecord is frozen/immutable, so returning a new list is safe).
        """
        with self._lock:
            return list(self._cache.values())

    def get_vision_registry(self) -> List[Dict[str, str]]:
        """
        Returns ONLY identities eligible for Vision (enabled AND face_enrolled).
        Yields only necessary fields: person_id, display_name, role.
        """
        with self._lock:
            vision_list = []
            for record in self._cache.values():
                if record.enabled and record.face_enrolled:
                    vision_list.append({
                        "person_id": record.person_id,
                        "display_name": record.display_name,
                        "role": record.role
                    })
            return vision_list

    def mark_face_enrolled(self, person_id: str) -> bool:
        """
        Updates an existing identity to reflect face enrollment.
        Returns False if the identity does not exist.
        """
        with self._lock:
            if person_id not in self._cache:
                return False
            old_record = self._cache[person_id]
            self._cache[person_id] = replace(old_record, face_enrolled=True)
            self._trigger_mutations()
            return True

    def mark_face_removed(self, person_id: str) -> bool:
        """
        Updates an existing identity to reflect removal of face enrollment.
        Returns False if the identity does not exist.
        """
        with self._lock:
            if person_id not in self._cache:
                return False
            old_record = self._cache[person_id]
            self._cache[person_id] = replace(old_record, face_enrolled=False)
            self._trigger_mutations()
            return True

    def remove_identity(self, person_id: str) -> bool:
        """
        Removes an identity from the cache.
        Returns True if removed, False if it wasn't there.
        """
        with self._lock:
            if person_id in self._cache:
                del self._cache[person_id]
                self._trigger_mutations()
                return True
            return False

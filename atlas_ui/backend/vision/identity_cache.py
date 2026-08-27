import threading
import copy
from typing import Dict, Any, List

class IdentityCache:
    """
    In-memory thread-safe cache for authoritative identities synchronized from ATLAS OS.
    Vision node uses this for read-only lookups.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._identities: Dict[str, Dict[str, Any]] = {}
        self._version: int = 0

    def update_snapshot(self, version: int, persons: List[Dict[str, Any]]) -> bool:
        with self._lock:
            if version == 0:
                self._version = 0
                self._identities.clear()
                
            # Idempotent/Stale check
            if version < self._version:
                return False  # Stale payload
            if version == self._version and self._identities:
                return True   # Idempotent duplicate
                
            new_state = {}
            for p in persons:
                # Reject invalid IDs
                if not p.get("person_id", "").startswith("ATLAS-P-"):
                    continue
                new_state[p["person_id"]] = copy.deepcopy(p)
                
            self._identities = new_state
            self._version = version
            return True

    def get_identity(self, person_id: str) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._identities.get(person_id))

    def get_all(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(v) for v in self._identities.values()]

class BiometricCache:
    """
    In-memory thread-safe cache for biometric templates synchronized from ATLAS OS.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._version: int = 0
        self._recognizer = ""

    def update_snapshot(self, version: int, recognizer: str, templates: Dict[str, Dict[str, Any]]) -> bool:
        with self._lock:
            if version == 0:
                self._version = 0
                self._templates.clear()
                
            if version < self._version:
                return False
            if version == self._version and self._templates:
                return True
                
            new_state = {}
            for person_id, data in templates.items():
                if not person_id.startswith("ATLAS-P-"):
                    continue
                new_state[person_id] = copy.deepcopy(data)
                
            self._templates = new_state
            self._recognizer = recognizer
            self._version = version
            return True

    def get_templates(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._templates)

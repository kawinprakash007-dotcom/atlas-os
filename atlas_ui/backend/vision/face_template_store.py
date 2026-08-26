import os
import json
import shutil
import time
from typing import Dict, List, Any, Optional
from enum import Enum

# Recognizer ID for templates produced by InsightFace buffalo_l
RECOGNIZER_ID = "insightface_buffalo_l"


class TemplateStatus(str, Enum):
    NOT_ENROLLED = "NOT_ENROLLED"
    ENROLLED = "ENROLLED"
    LEGACY_TEMPLATE = "LEGACY_TEMPLATE"      # no recognizer field — old garavv model
    RE_ENROLLMENT_REQUIRED = "RE_ENROLLMENT_REQUIRED"  # recognizer mismatch
    CORRUPTED_TEMPLATE = "CORRUPTED_TEMPLATE"


class FaceTemplateStore:
    """
    Manages persistence of face templates in JSON format with atomic writes.

    Template record schema (v2):
    {
        "recognizer": "insightface_buffalo_l",
        "embedding_dimension": 512,
        "template_count": 5,
        "enrolled_at": "...",
        "templates": [[...], [...], ...]
    }

    Legacy templates (v1, produced by garavv/arcface-onnx) have no "recognizer"
    field. They are detected and reported as LEGACY_TEMPLATE / RE_ENROLLMENT_REQUIRED.
    They are NEVER compared with new embeddings.
    """

    def __init__(self, store_path: Optional[str] = None):
        if store_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            store_path = os.path.abspath(
                os.path.join(current_dir, "..", "data", "face_templates.json")
            )

        self.store_path = store_path
        self._data: Dict[str, Any] = {"version": 2, "people": {}}
        self._load_store()

    # ------------------------------------------------------------------
    # I/O
    # ------------------------------------------------------------------

    def _load_store(self) -> None:
        if not os.path.exists(self.store_path):
            self._data = {"version": 2, "people": {}}
            return

        try:
            with open(self.store_path, "r") as f:
                loaded = json.load(f)

            if not isinstance(loaded, dict) or "people" not in loaded:
                raise ValueError("Template store JSON is missing 'people' key.")

            people = loaded["people"]
            if not isinstance(people, dict):
                raise ValueError("'people' key must be a dictionary.")

            for person_id, record in people.items():
                if not isinstance(record, dict) or "templates" not in record or "embedding_dimension" not in record:
                    raise ValueError(f"Malformed template record for person {person_id}.")

                dim = record["embedding_dimension"]
                templates = record["templates"]
                if not isinstance(templates, list):
                    raise ValueError(f"Templates for person {person_id} must be a list.")

                for i, t in enumerate(templates):
                    if not isinstance(t, list) or len(t) != dim:
                        raise ValueError(
                            f"Template {i} for person {person_id} has dimension {len(t)} (expected {dim})."
                        )

            self._data = loaded
            print(
                f"[TEMPLATE STORE] Loaded {len(self._data['people'])} people from {self.store_path}.",
                flush=True
            )

        except Exception as e:
            raise ValueError(f"Failed to load/parse templates database at {self.store_path}: {e}")

    def _save_store(self) -> None:
        dir_name = os.path.dirname(self.store_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        tmp_path = self.store_path + f".{time.time_ns()}.tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(self._data, f, indent=4)
            shutil.move(tmp_path, self.store_path)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise IOError(f"Failed to save templates database atomically: {e}")

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    def save_templates(
        self,
        person_id: str,
        templates: List[List[float]],
        recognizer: str = RECOGNIZER_ID,
        overwrite: bool = False,
    ) -> None:
        """
        Saves face templates with full metadata (recognizer, dimension, timestamp).
        Raises ValueError if templates already exist and overwrite=False.
        """
        if not templates:
            raise ValueError("Cannot save an empty list of templates.")

        if self.has_templates(person_id) and not overwrite:
            raise ValueError(f"Face templates already exist for person '{person_id}'.")

        dim = len(templates[0])
        for i, t in enumerate(templates):
            if len(t) != dim:
                raise ValueError(
                    f"Template {i} has inconsistent dimension {len(t)} (expected {dim})."
                )

        self._data["people"][person_id] = {
            "recognizer": recognizer,
            "embedding_dimension": dim,
            "enrolled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "template_count": len(templates),
            "templates": templates,
        }

        self._save_store()
        print(
            f"[TEMPLATE STORE] Saved {len(templates)} templates for '{person_id}' "
            f"(recognizer={recognizer}, dim={dim}).",
            flush=True
        )

    def remove_templates(self, person_id: str) -> bool:
        if person_id in self._data["people"]:
            del self._data["people"][person_id]
            self._save_store()
            print(f"[TEMPLATE STORE] Removed templates for '{person_id}'.", flush=True)
            return True
        return False

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def has_templates(self, person_id: str) -> bool:
        """True if any templates exist — regardless of recognizer compatibility."""
        return person_id in self._data["people"]

    def get_template_status(
        self, person_id: str, expected_recognizer: str = RECOGNIZER_ID
    ) -> TemplateStatus:
        """
        Returns a structured status describing the template state for person_id.

        Possible return values:
            NOT_ENROLLED           — no templates found
            ENROLLED               — templates present with matching recognizer
            LEGACY_TEMPLATE        — templates present but no recognizer field (old model)
            RE_ENROLLMENT_REQUIRED — templates present but wrong recognizer
            CORRUPTED_TEMPLATE     — templates present but malformed
        """
        if person_id not in self._data["people"]:
            return TemplateStatus.NOT_ENROLLED

        record = self._data["people"][person_id]

        # Structural validation
        if not isinstance(record.get("templates"), list) or not record["templates"]:
            return TemplateStatus.CORRUPTED_TEMPLATE

        # Legacy detection (no recognizer field)
        stored_recognizer = record.get("recognizer")
        if stored_recognizer is None:
            return TemplateStatus.LEGACY_TEMPLATE

        # Recognizer mismatch
        if stored_recognizer != expected_recognizer:
            return TemplateStatus.RE_ENROLLMENT_REQUIRED

        return TemplateStatus.ENROLLED

    def get_templates(self, person_id: str) -> Optional[List[List[float]]]:
        """
        Returns the raw template list.
        Callers MUST check get_template_status() == ENROLLED before calling this
        to ensure the templates are compatible with the current recognizer.
        """
        record = self._data["people"].get(person_id)
        if record:
            return record.get("templates")
        return None

    def get_recognizer(self, person_id: str) -> Optional[str]:
        """Returns the recognizer identifier stored with the templates, or None."""
        record = self._data["people"].get(person_id)
        if record:
            return record.get("recognizer")
        return None

    def get_embedding_dimension(self, person_id: str) -> Optional[int]:
        record = self._data["people"].get(person_id)
        if record:
            return record.get("embedding_dimension")
        return None

    def list_enrolled_people(self) -> List[str]:
        return list(self._data["people"].keys())

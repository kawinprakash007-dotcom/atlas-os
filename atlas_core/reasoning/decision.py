import uuid
import dataclasses
from typing import List, Dict, Any, Optional

@dataclasses.dataclass
class Decision:
    decision_id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
    situation_summary: str = ""
    observations: List[str] = dataclasses.field(default_factory=list)
    inferences: List[str] = dataclasses.field(default_factory=list)
    risks: List[str] = dataclasses.field(default_factory=list)
    recommended_actions: List[Dict[str, Any]] = dataclasses.field(default_factory=list)
    confidence: float = 1.0
    requires_deep_analysis: bool = False
    decision_rationale: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)

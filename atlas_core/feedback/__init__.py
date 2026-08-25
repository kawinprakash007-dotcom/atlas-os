from typing import List
from dataclasses import dataclass, field

@dataclass
class ExecutionFeedbackResult:
    processed_actions: int
    successful_actions: int
    failed_actions: int
    world_state_updated: bool
    history_recorded: bool
    memory_stored: bool
    skipped: bool
    errors: List[str] = field(default_factory=list)

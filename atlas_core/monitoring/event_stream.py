import uuid
import time
import copy
from typing import Dict, List, Optional, Any
from atlas_core.monitoring.models import EventTrace
from atlas_core.monitoring.metrics import SystemMetrics

class EventStream:
    def __init__(self, max_history: int = 1000, metrics: Optional[SystemMetrics] = None):
        self.max_history = max_history
        self.metrics = metrics or SystemMetrics()
        self._traces: List[EventTrace] = []
        self._trace_map: Dict[str, EventTrace] = {}

    def create_event(
        self,
        event_type: str,
        source: str,
        metadata: Optional[dict] = None
    ) -> EventTrace:
        trace_id = str(uuid.uuid4())
        trace = EventTrace(
            trace_id=trace_id,
            event_type=event_type,
            source=source,
            received_at=time.time(),
            status="RECEIVED",
            metadata=dict(metadata) if metadata is not None else {}
        )
        self._traces.append(trace)
        self._trace_map[trace_id] = trace

        # Bounded history check
        while len(self._traces) > self.max_history:
            removed = self._traces.pop(0)
            self._trace_map.pop(removed.trace_id, None)

        self.metrics.total_events += 1
        return copy.deepcopy(trace)

    def _get_internal(self, trace_id: str) -> EventTrace:
        if trace_id not in self._trace_map:
            raise KeyError(f"Trace ID '{trace_id}' not found.")
        return self._trace_map[trace_id]

    def mark_validated(self, trace_id: str) -> EventTrace:
        trace = self._get_internal(trace_id)
        if trace.status in ("REJECTED", "FAILED", "COMPLETED"):
            raise ValueError(f"Cannot transition trace '{trace_id}' from terminal state '{trace.status}'.")
        if trace.status == "VALIDATED":
            # Idempotency check: don't double count if already in VALIDATED status
            return copy.deepcopy(trace)

        trace.status = "VALIDATED"
        trace.validated = True
        self.metrics.validated_events += 1
        return copy.deepcopy(trace)

    def mark_device_verified(self, trace_id: str) -> EventTrace:
        trace = self._get_internal(trace_id)
        if trace.status in ("REJECTED", "FAILED", "COMPLETED"):
            raise ValueError(f"Cannot transition trace '{trace_id}' from terminal state '{trace.status}'.")
        if trace.status == "DEVICE_VERIFIED":
            return copy.deepcopy(trace)

        trace.status = "DEVICE_VERIFIED"
        trace.device_verified = True
        return copy.deepcopy(trace)

    def mark_processing(self, trace_id: str) -> EventTrace:
        trace = self._get_internal(trace_id)
        if trace.status in ("REJECTED", "FAILED", "COMPLETED"):
            raise ValueError(f"Cannot transition trace '{trace_id}' from terminal state '{trace.status}'.")
        trace.status = "PROCESSING"
        return copy.deepcopy(trace)

    def mark_rejected(self, trace_id: str, error: Optional[str] = None) -> EventTrace:
        trace = self._get_internal(trace_id)
        if trace.status in ("REJECTED", "FAILED", "COMPLETED"):
            raise ValueError(f"Cannot transition trace '{trace_id}' from terminal state '{trace.status}'.")

        trace.status = "REJECTED"
        trace.error = error
        trace.completed_at = time.time()
        self.metrics.rejected_events += 1
        return copy.deepcopy(trace)

    def mark_failed(self, trace_id: str, error: str) -> EventTrace:
        trace = self._get_internal(trace_id)
        if trace.status in ("REJECTED", "FAILED", "COMPLETED"):
            raise ValueError(f"Cannot transition trace '{trace_id}' from terminal state '{trace.status}'.")

        trace.status = "FAILED"
        trace.error = error
        trace.completed_at = time.time()
        self.metrics.failed_events += 1
        return copy.deepcopy(trace)

    def mark_runtime_result(self, trace_id: str, result: Dict[str, Any]) -> EventTrace:
        trace = self._get_internal(trace_id)
        if trace.status in ("REJECTED", "FAILED", "COMPLETED"):
            raise ValueError(f"Cannot transition trace '{trace_id}' from terminal state '{trace.status}'.")

        # 1. Extract verdict from runtime result
        verdict = "BLOCKED"
        reasoning_result = result.get("reasoning_result")
        if reasoning_result:
            arb_res = getattr(reasoning_result, "arbitration_result", None)
            if arb_res:
                verdict = getattr(arb_res, "verdict", "BLOCKED")
            else:
                if getattr(reasoning_result, "blocked", False):
                    verdict = "BLOCKED"
                elif getattr(reasoning_result, "action_review_required", False):
                    verdict = "REVIEW"
                else:
                    verdict = "APPROVED"

        # 2. Extract action status from runtime result
        action_status = "NO_ACTION"
        action_exec_result = result.get("action_execution_result")
        if action_exec_result:
            failed_actions = getattr(action_exec_result, "failed_actions", None)
            executed_actions = getattr(action_exec_result, "executed_actions", None)
            if failed_actions:
                action_status = "FAILED"
            elif executed_actions:
                action_status = "EXECUTED"
            else:
                action_status = "NO_ACTION"

        trace.verdict = verdict
        trace.action_status = action_status
        trace.status = "COMPLETED"
        trace.completed_at = time.time()

        # Update metrics atomically exactly once
        if verdict == "APPROVED":
            self.metrics.approved_events += 1
        elif verdict == "REVIEW":
            self.metrics.review_events += 1
        elif verdict == "BLOCKED":
            self.metrics.blocked_events += 1

        if action_status == "EXECUTED":
            self.metrics.actions_executed += 1
        elif action_status == "FAILED":
            self.metrics.actions_failed += 1
        elif action_status == "NO_ACTION":
            self.metrics.no_action_events += 1

        return copy.deepcopy(trace)

    def get_event(self, trace_id: str) -> Optional[EventTrace]:
        trace = self._trace_map.get(trace_id)
        if trace is None:
            return None
        return copy.deepcopy(trace)

    def list_recent(self, limit: int = 50) -> List[EventTrace]:
        limit = max(1, min(limit, self.max_history))
        recent = self._traces[-limit:]
        return [copy.deepcopy(t) for t in recent]

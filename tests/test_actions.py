import pytest
from atlas_core.actions.registry import ActionRegistry, ActionDefinition
from atlas_core.actions.safety import ActionSafetyValidator, ActionSafetyResult
from atlas_core.actions.dispatcher import ActionDispatcher, ActionExecutionResult
from atlas_core.reasoning.arbitration import ArbitrationResult

def dummy_handler(payload):
    return {"status": "success", "payload_received": payload}

def failing_handler(payload):
    raise ValueError("Handler failed")

def mutating_handler(payload):
    payload["mutated"] = True
    return payload

@pytest.fixture
def registry():
    r = ActionRegistry()
    r.register("activate_cooling", ["device_id"], dummy_handler)
    r.register("failing_action", ["id"], failing_handler)
    r.register("mutating_action", ["id"], mutating_handler)
    r.register("no_handler", ["id"])
    return r

def test_registry_register_and_lookup(registry):
    action = registry.get_action("activate_cooling")
    assert action is not None
    assert action.action_type == "activate_cooling"
    assert "device_id" in action.required_fields

def test_registry_unknown_action(registry):
    assert registry.get_action("unknown") is None
    assert not registry.is_registered("unknown")

def test_registry_duplicate_registration(registry):
    with pytest.raises(ValueError):
        registry.register("activate_cooling", [])

def _create_arbitration(verdict, allowed_actions):
    return ArbitrationResult(
        verdict=verdict,
        approved=(verdict=="APPROVED"),
        blocked=(verdict=="BLOCKED"),
        requires_human_review=(verdict=="REVIEW"),
        allowed_actions=allowed_actions,
        blocked_actions=[],
        reasons=[],
        confidence=1.0,
        grounding_status="TRUSTED",
        source="test"
    )

def test_safety_approved_valid_action(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("APPROVED", [{"action_type": "activate_cooling", "payload": {"device_id": "d1"}}])
    result = validator.validate(arb)
    
    assert result.safe is True
    assert len(result.allowed_actions) == 1
    assert len(result.blocked_actions) == 0

def test_safety_review_blocked(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("REVIEW", [{"action_type": "activate_cooling", "payload": {"device_id": "d1"}}])
    result = validator.validate(arb)
    
    assert result.safe is False
    assert len(result.allowed_actions) == 0
    assert len(result.blocked_actions) == 1

def test_safety_blocked_blocked(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("BLOCKED", [{"action_type": "activate_cooling", "payload": {"device_id": "d1"}}])
    result = validator.validate(arb)
    
    assert result.safe is False
    assert len(result.allowed_actions) == 0
    assert len(result.blocked_actions) == 1

def test_safety_unknown_action(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("APPROVED", [{"action_type": "unknown", "payload": {}}])
    result = validator.validate(arb)
    
    assert result.safe is False
    assert len(result.blocked_actions) == 1
    assert "Unknown action type" in result.reasons[0]

def test_safety_missing_action_type(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("APPROVED", [{"payload": {}}])
    result = validator.validate(arb)
    
    assert result.safe is False
    assert len(result.blocked_actions) == 1
    assert "Action missing 'action_type'" in result.reasons[0]

def test_safety_missing_payload(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("APPROVED", [{"action_type": "activate_cooling"}])
    result = validator.validate(arb)
    
    assert result.safe is False
    assert len(result.blocked_actions) == 1
    assert "missing 'payload'" in result.reasons[0]

def test_safety_payload_not_dictionary(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("APPROVED", [{"action_type": "activate_cooling", "payload": "string_payload"}])
    result = validator.validate(arb)
    
    assert result.safe is False
    assert len(result.blocked_actions) == 1

def test_safety_missing_required_field(registry):
    validator = ActionSafetyValidator(registry)
    arb = _create_arbitration("APPROVED", [{"action_type": "activate_cooling", "payload": {"wrong_field": "d1"}}])
    result = validator.validate(arb)
    
    assert result.safe is False
    assert len(result.blocked_actions) == 1
    assert "missing required payload fields" in result.reasons[0]

def test_dispatcher_successful_execution(registry):
    dispatcher = ActionDispatcher(registry)
    safety_res = ActionSafetyResult(True, [{"action_type": "activate_cooling", "payload": {"device_id": "d1"}}], [], [])
    
    results = dispatcher.dispatch(safety_res)
    assert len(results) == 1
    assert results[0].status == "SUCCESS"
    assert results[0].result["payload_received"]["device_id"] == "d1"

def test_dispatcher_handler_exception(registry):
    dispatcher = ActionDispatcher(registry)
    safety_res = ActionSafetyResult(True, [{"action_type": "failing_action", "payload": {"id": "1"}}], [], [])
    
    results = dispatcher.dispatch(safety_res)
    assert len(results) == 1
    assert results[0].status == "FAILED"
    assert "Handler failed" in results[0].error

def test_dispatcher_multiple_actions(registry):
    dispatcher = ActionDispatcher(registry)
    safety_res = ActionSafetyResult(True, [
        {"action_type": "activate_cooling", "payload": {"device_id": "d1"}},
        {"action_type": "failing_action", "payload": {"id": "1"}}
    ], [], [])
    
    results = dispatcher.dispatch(safety_res)
    assert len(results) == 2
    assert results[0].status == "SUCCESS"
    assert results[1].status == "FAILED"

def test_dispatcher_safe_payload_copying(registry):
    dispatcher = ActionDispatcher(registry)
    payload = {"id": "1"}
    safety_res = ActionSafetyResult(True, [{"action_type": "mutating_action", "payload": payload}], [], [])
    
    results = dispatcher.dispatch(safety_res)
    assert len(results) == 1
    assert results[0].status == "SUCCESS"
    
    # Original payload must remain untouched
    assert "mutated" not in payload

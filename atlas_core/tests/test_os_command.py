import pytest
from atlas_core.actions.os_command import os_command_handler

def test_os_command_handler_string_payload():
    payload = {"command": "echo Hello"}
    result = os_command_handler(payload)
    assert result["success"] is True
    assert "Hello" in result["stdout"]

def test_os_command_handler_list_payload():
    payload = {"command": ["echo", "Hello from list"]}
    result = os_command_handler(payload)
    assert result["success"] is True
    assert "Hello from list" in result["stdout"]

def test_os_command_handler_ping():
    payload = {"command": "ping 127.0.0.1"}
    result = os_command_handler(payload)
    # Just need it to execute successfully without shell=True
    # Using 127.0.0.1 since it's local and fast
    assert result["success"] is True

def test_os_command_handler_invalid():
    payload = {"command": "invalidcmd"}
    with pytest.raises(PermissionError):
        os_command_handler(payload)

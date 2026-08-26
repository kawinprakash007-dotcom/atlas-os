import subprocess
from typing import Dict, Any, List
import shlex

ALLOWED_COMMANDS = [
    "ping",
    "ipconfig",
    "dir",
    "echo",
    "systeminfo",
    "netstat"
]

def _normalize_command(command_input: Any) -> List[str]:
    """
    Safely normalizes the command input to a structured argument list.
    Supports backward compatibility if a string is provided.
    """
    if isinstance(command_input, list):
        return [str(arg) for arg in command_input]
    elif isinstance(command_input, str):
        # Safely split the string into an argument list
        return shlex.split(command_input)
    else:
        raise ValueError(f"Unsupported command format: {type(command_input)}")

def os_command_handler(payload: Dict[str, Any]) -> Dict[str, Any]:
    raw_command = payload.get("command")
    if not raw_command:
        raise ValueError("Command is required")
        
    cmd_list = _normalize_command(raw_command)
    if not cmd_list:
        raise ValueError("Command cannot be empty")
        
    base_cmd = cmd_list[0].lower()
    
    # Windows built-in commands require cmd /c when shell=False
    if base_cmd in ["dir", "echo"]:
        cmd_list = ["cmd.exe", "/c"] + cmd_list
    elif base_cmd not in ALLOWED_COMMANDS:
        raise PermissionError(f"Command '{base_cmd}' is not in the allowed whitelist.")
        
    # Re-check whitelist against the actual command (in case cmd /c was prepended)
    actual_base_cmd = base_cmd
    if actual_base_cmd not in ALLOWED_COMMANDS:
        raise PermissionError(f"Command '{actual_base_cmd}' is not in the allowed whitelist.")

    try:
        # Run command safely without shell=True
        result = subprocess.run(
            cmd_list,
            shell=False,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "success": result.returncode == 0
        }
    except subprocess.TimeoutExpired:
        raise TimeoutError(f"Command '{raw_command}' timed out after 10 seconds.")
    except Exception as e:
        raise RuntimeError(f"Command execution failed: {str(e)}")

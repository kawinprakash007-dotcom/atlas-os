import pytest
from atlas_core.monitoring.system_awareness import SystemMonitor

def test_system_awareness_telemetry():
    monitor = SystemMonitor()
    telemetry = monitor.get_telemetry()
    
    # Assert top-level keys
    assert "cpu" in telemetry
    assert "memory" in telemetry
    assert "disk" in telemetry
    assert "os" in telemetry
    assert "network" in telemetry
    
    # Assert CPU values
    assert isinstance(telemetry["cpu"]["usage_percent"], float)
    assert isinstance(telemetry["cpu"]["cores"], int)
    assert telemetry["cpu"]["cores"] > 0
    
    # Assert Memory values
    assert isinstance(telemetry["memory"]["usage_percent"], float)
    assert isinstance(telemetry["memory"]["available_gb"], float)
    
    # Assert Disk values
    assert isinstance(telemetry["disk"]["usage_percent"], float)
    assert isinstance(telemetry["disk"]["free_gb"], float)
    
    # Assert OS values
    assert isinstance(telemetry["os"]["info"], str)
    assert isinstance(telemetry["os"]["hostname"], str)
    assert isinstance(telemetry["os"]["uptime_seconds"], float)
    
    # Assert Network values
    assert isinstance(telemetry["network"]["status"], str)
    assert isinstance(telemetry["network"]["local_ip"], str)
    assert telemetry["network"]["status"] in ["Connected", "Disconnected"]
    assert len(telemetry["network"]["local_ip"]) > 0

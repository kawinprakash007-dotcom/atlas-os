export function renderSystemStatus(systemStatus, role) {
    return `
        <div class="panel-card glass-panel" style="position: relative;">
            <div class="card-title">System Awareness Telemetry</div>
            <div class="status-item">
                <span>CPU Usage</span>
                <span id="telemetry-cpu" style="color: #39ff14; font-weight: bold;">--%</span>
            </div>
            <div class="status-item">
                <span>Memory Available</span>
                <span id="telemetry-ram" style="color: var(--accent-color); font-weight: bold;">-- GB</span>
            </div>
            <div class="status-item">
                <span>Disk Free</span>
                <span id="telemetry-disk" style="color: #39ff14; font-weight: bold;">-- GB</span>
            </div>
            <div class="status-item">
                <span>Network IP</span>
                <span id="telemetry-ip" style="color: var(--accent-color); font-weight: bold;">--</span>
            </div>
            <div class="status-item">
                <span>System Uptime</span>
                <span id="telemetry-uptime" style="color: var(--accent-color); font-weight: bold;">--</span>
            </div>
        </div>
    `;
}

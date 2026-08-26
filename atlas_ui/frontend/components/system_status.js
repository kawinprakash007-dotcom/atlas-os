export function renderSystemStatus(systemStatus, role) {
    return `
        <div class="panel-card glass-panel">
            <div class="card-title">System Status Overview</div>
            <div class="status-item">
                <span>Core Operating Status</span>
                <span style="color: #39ff14; font-weight: bold;">${systemStatus}</span>
            </div>
            <div class="status-item">
                <span>ATLAS Reasoning Mode</span>
                <span style="color: var(--accent-color); font-weight: bold;">AUTONOMOUS</span>
            </div>
            <div class="status-item">
                <span>Active Network Gateway</span>
                <span style="color: #39ff14; font-weight: bold;">ONLINE</span>
            </div>
            <div class="status-item">
                <span>Biometric Profile Match</span>
                <span style="color: var(--accent-color); font-weight: bold;">CONFIRMED</span>
            </div>
            <div class="status-item">
                <span>Session Clearance</span>
                <span style="color: var(--accent-color); font-weight: bold; text-transform: uppercase;">${role}</span>
            </div>
        </div>
    `;
}

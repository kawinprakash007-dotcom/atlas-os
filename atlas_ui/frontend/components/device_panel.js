export function renderDevicePanel(devices) {
    if (!devices || devices.length === 0) {
        return `
            <div class="panel-card glass-panel">
                <div class="card-title">Registered Devices</div>
                <div style="color: var(--text-secondary); font-size: 0.9rem; text-align: center; padding: 30px 0;">
                    No devices discovered in registry.
                </div>
            </div>
        `;
    }
    
    const list = devices.map(d => `
        <div class="device-item">
            <div>
                <strong style="display: block; font-family: var(--font-heading); font-size: 0.95rem;">${d.device_id}</strong>
                <span style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">
                    Type: ${d.device_type}
                </span>
            </div>
            <div>
                <span class="badge-online">${d.status}</span>
            </div>
        </div>
    `).join('');

    return `
        <div class="panel-card glass-panel">
            <div class="card-title">Registered Devices</div>
            <div style="max-height: 300px; overflow-y: auto;">
                ${list}
            </div>
        </div>
    `;
}

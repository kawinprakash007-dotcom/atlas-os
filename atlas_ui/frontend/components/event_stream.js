export function renderEventStream(events, alerts) {
    const alertItems = (alerts || []).map(a => `
        <div class="alert-item">
            <div class="event-meta">
                <span style="color: var(--accent-danger); font-weight: bold;">[${a.severity}]</span>
                <span>${a.timestamp}</span>
            </div>
            <div class="event-details">${a.message}</div>
        </div>
    `).join('');

    const eventItems = (events || []).map(e => `
        <div class="event-item">
            <div class="event-meta">
                <span style="color: var(--accent-color);">[EVENT]</span>
                <span>${e.timestamp}</span>
            </div>
            <div class="event-details">
                <strong>${e.event_type}</strong> triggered by <em>${e.source}</em>
            </div>
        </div>
    `).join('');

    return `
        <div class="panel-card glass-panel">
            <div class="card-title">Live Diagnostics Log</div>
            <div style="max-height: 320px; overflow-y: auto;">
                ${alertItems}
                ${eventItems}
                ${alertItems.length === 0 && eventItems.length === 0 ? `
                    <div style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 30px 0;">
                        Diagnostics clear. No active events.
                    </div>
                ` : ''}
            </div>
        </div>
    `;
}

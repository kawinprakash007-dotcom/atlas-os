import { renderSidebar } from "../components/sidebar.js";
import { renderDevicePanel } from "../components/device_panel.js";
import { renderEventStream } from "../components/event_stream.js";
import { renderSystemStatus } from "../components/system_status.js";
import { renderUserManagement } from "../components/UserManagement.js";
import { renderAssistantPanel } from "../components/AssistantPanel.js";
import { renderVisionPanel } from "../components/VisionPanel.js";

export function renderAdminDashboard(role, sessionId, onLogout) {
    const appEl = document.getElementById("app");
    
    let activeTab = "overview";
    let cachedDashboardData = null;
    let visionCleanup = null;
    
    appEl.innerHTML = `
        <div class="dashboard-wrapper">
            <div id="sidebar-container"></div>
            <main class="dashboard-main">
                <header class="panel-header">
                    <h1 class="panel-title">Admin Command Center</h1>
                    <span style="font-family: var(--font-heading); color: var(--accent-danger); text-shadow: 0 0 5px var(--accent-danger-glow);">
                         clearance: superuser
                    </span>
                </header>
                <div class="dashboard-grid" id="dashboard-content">
                    <div style="grid-column: span 2; text-align: center; padding: 50px 0;">
                        <span style="color: var(--accent-color);">INITIALIZING FEED TELEMETRY...</span>
                    </div>
                </div>
            </main>
        </div>
    `;

    function updateSidebar() {
        document.getElementById("sidebar-container").innerHTML = renderSidebar(role, activeTab);
        attachSidebarListeners();
        document.getElementById("btn-logout").addEventListener("click", () => {
            if (visionCleanup) {
                try { visionCleanup(); } catch(e) {}
                visionCleanup = null;
            }
            onLogout();
        });
    }

    function attachSidebarListeners() {
        const tabs = ["overview", "devices", "events", "users", "vision", "security", "config"];
        tabs.forEach(tab => {
            const el = document.getElementById(`nav-${tab}`);
            if (el) {
                el.addEventListener("click", (e) => {
                    e.preventDefault();
                    if (activeTab !== tab) {
                        if (visionCleanup) {
                            try { visionCleanup(); } catch(e) {}
                            visionCleanup = null;
                        }
                        activeTab = tab;
                        updateSidebar();
                        renderContent();
                    }
                });
            }
        });
    }

    async function fetchDashboardData() {
        try {
            const response = await fetch("/api/v1/dashboard", {
                method: "GET",
                headers: { "Authorization": `Bearer ${sessionId}` }
            });
            if (!response.ok) throw new Error("Failed to load dashboard statistics.");
            cachedDashboardData = await response.json();
        } catch (err) {
            document.getElementById("dashboard-content").innerHTML = `
                <div style="grid-column: span 2; text-align: center; color: var(--accent-danger); padding: 50px 0;">
                    ${err.message || "Failed to load telemetry."}
                </div>
            `;
            throw err;
        }
    }

    async function renderContent() {
        const contentEl = document.getElementById("dashboard-content");
        
        try {
            if (activeTab === "overview") {
                if (!cachedDashboardData) await fetchDashboardData();
                contentEl.innerHTML = `
                    <div class="grid-col">
                        ${renderSystemStatus(cachedDashboardData.system_status, cachedDashboardData.role)}
                        <div style="margin-top: 25px;"></div>
                        ${renderDevicePanel(cachedDashboardData.devices)}
                    </div>
                    <div class="grid-col">
                        ${renderEventStream(cachedDashboardData.recent_events, cachedDashboardData.alerts)}
                    </div>
                `;
            } else if (activeTab === "users") {
                contentEl.innerHTML = `<div id="user-management-container" style="grid-column: span 2;"></div>`;
                renderUserManagement("user-management-container", sessionId, () => {});
            } else if (activeTab === "devices") {
                if (!cachedDashboardData) await fetchDashboardData();
                contentEl.innerHTML = `
                    <div style="grid-column: span 2;">
                        ${renderDevicePanel(cachedDashboardData.devices)}
                    </div>
                `;
            } else if (activeTab === "events") {
                if (!cachedDashboardData) await fetchDashboardData();
                contentEl.innerHTML = `
                    <div style="grid-column: span 2;">
                        ${renderEventStream(cachedDashboardData.recent_events, cachedDashboardData.alerts)}
                    </div>
                `;
            } else if (activeTab === "security") {
                contentEl.innerHTML = `
                    <div class="glass-panel" style="grid-column: span 2; padding: 40px; text-align: center;">
                        <i class="fas fa-shield-alt" style="font-size: 3em; color: var(--accent-color); margin-bottom: 20px;"></i>
                        <h2 style="font-family: var(--font-heading); color: var(--text-primary); margin-top: 0;">Security Logs</h2>
                        <p style="color: var(--text-secondary); max-width: 600px; margin: 0 auto 20px;">Live audit trails and security events are currently streaming to cold storage. Real-time view coming online in next update.</p>
                        <button class="btn-secondary" onclick="alert('Querying logs... (Coming Soon)')"><i class="fas fa-search"></i> QUERY LOGS</button>
                    </div>
                `;
            } else if (activeTab === "config") {
                contentEl.innerHTML = `
                    <div class="glass-panel" style="grid-column: span 2; padding: 40px; text-align: center;">
                        <i class="fas fa-cogs" style="font-size: 3em; color: var(--accent-color); margin-bottom: 20px;"></i>
                        <h2 style="font-family: var(--font-heading); color: var(--text-primary); margin-top: 0;">System Configuration</h2>
                        <p style="color: var(--text-secondary); max-width: 600px; margin: 0 auto 20px;">Global system parameters, biometric thresholds, and API keys.</p>
                        <div style="display: flex; justify-content: center; gap: 10px;">
                            <button class="btn-secondary" disabled>BIOMETRICS CONFIG</button>
                            <button class="btn-secondary" disabled>NETWORK CONFIG</button>
                        </div>
                    </div>
                `;
            } else if (activeTab === "vision") {
                contentEl.innerHTML = `<div id="vision-dashboard-container" style="grid-column: span 2;"></div>`;
                visionCleanup = renderVisionPanel("vision-dashboard-container", sessionId);
            }
        } catch (e) {
            // error already displayed by fetchDashboardData
        }
    }

    // Initialize
    updateSidebar();
    renderContent();
    
    // Add Assistant Panel
    renderAssistantPanel(appEl, sessionId);

    // Telemetry WebSocket
    function connectTelemetryWs() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/events`;
        const telemetryWs = new WebSocket(wsUrl);

        telemetryWs.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "system_telemetry" && data.data) {
                    const tData = data.data;
                    const cpuEl = document.getElementById("telemetry-cpu");
                    const ramEl = document.getElementById("telemetry-ram");
                    const diskEl = document.getElementById("telemetry-disk");
                    const ipEl = document.getElementById("telemetry-ip");
                    const uptimeEl = document.getElementById("telemetry-uptime");

                    if (cpuEl) cpuEl.innerText = `${tData.cpu.usage_percent.toFixed(1)}% (${tData.cpu.cores}C)`;
                    if (ramEl) ramEl.innerText = `${tData.memory.available_gb.toFixed(1)} GB`;
                    if (diskEl) diskEl.innerText = `${tData.disk.free_gb.toFixed(1)} GB`;
                    if (ipEl) ipEl.innerText = `${tData.network.local_ip}`;
                    
                    if (uptimeEl) {
                        const h = Math.floor(tData.os.uptime_seconds / 3600);
                        const m = Math.floor((tData.os.uptime_seconds % 3600) / 60);
                        uptimeEl.innerText = `${h}h ${m}m`;
                    }
                } else if (data.type === "system_event" && data.data) {
                    document.dispatchEvent(new CustomEvent("atlas-system-event", { detail: data.data }));
                }
            } catch(e) {}
        };
        telemetryWs.onclose = () => {
            setTimeout(connectTelemetryWs, 5000);
        };
    }
    connectTelemetryWs();
}

import { renderSidebar } from "../components/sidebar.js";
import { renderDevicePanel } from "../components/device_panel.js";
import { renderEventStream } from "../components/event_stream.js";
import { renderSystemStatus } from "../components/system_status.js";
import { renderUserManagement } from "../components/UserManagement.js";

export function renderAdminDashboard(role, sessionId, onLogout) {
    const appEl = document.getElementById("app");
    
    let activeTab = "overview";
    let cachedDashboardData = null;
    
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
            onLogout();
        });
    }

    function attachSidebarListeners() {
        const tabs = ["overview", "devices", "events", "users", "security", "config"];
        tabs.forEach(tab => {
            const el = document.getElementById(`nav-${tab}`);
            if (el) {
                el.addEventListener("click", (e) => {
                    e.preventDefault();
                    if (activeTab !== tab) {
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
            }
        } catch (e) {
            // error already displayed by fetchDashboardData
        }
    }

    // Initialize
    updateSidebar();
    renderContent();
}

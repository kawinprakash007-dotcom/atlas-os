import { renderSidebar } from "../components/sidebar.js";
import { renderDevicePanel } from "../components/device_panel.js";
import { renderEventStream } from "../components/event_stream.js";
import { renderSystemStatus } from "../components/system_status.js";
import { renderUserManagement } from "../components/UserManagement.js";

export function renderAdminDashboard(role, sessionId, onLogout) {
    const appEl = document.getElementById("app");
    
    appEl.innerHTML = `
        <div class="dashboard-wrapper">
            ${renderSidebar(role, "overview")}
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

    document.getElementById("btn-logout").addEventListener("click", () => {
        onLogout();
    });

    async function loadDashboardData() {
        try {
            const response = await fetch("/api/v1/dashboard", {
                method: "GET",
                headers: {
                    "Authorization": `Bearer ${sessionId}`
                }
            });

            if (!response.ok) {
                throw new Error("Failed to load dashboard statistics.");
            }

            const data = await response.json();
            
            const contentEl = document.getElementById("dashboard-content");
            contentEl.innerHTML = `
                <div class="grid-col">
                    ${renderSystemStatus(data.system_status, data.role)}
                    <div style="margin-top: 25px;"></div>
                    ${renderDevicePanel(data.devices)}
                </div>
                <div class="grid-col">
                    ${renderEventStream(data.recent_events, data.alerts)}
                </div>
                
                <!-- Admin specific operations card -->
                <div id="user-management-container" style="grid-column: span 2; margin-top: 20px;"></div>
            `;
            
            renderUserManagement("user-management-container", sessionId, loadDashboardData);
        } catch (err) {
            document.getElementById("dashboard-content").innerHTML = `
                <div style="grid-column: span 2; text-align: center; color: var(--accent-danger); padding: 50px 0;">
                    ${err.message || "Failed to load telemetry."}
                </div>
            `;
        }
    }

    loadDashboardData();
}

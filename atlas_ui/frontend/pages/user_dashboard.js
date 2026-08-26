import { renderSidebar } from "../components/sidebar.js";
import { renderDevicePanel } from "../components/device_panel.js";
import { renderEventStream } from "../components/event_stream.js";
import { renderSystemStatus } from "../components/system_status.js";
import { renderBiometricEnrollment } from "../components/BiometricEnrollment.js";
import { renderAssistantPanel } from "../components/AssistantPanel.js";

export function renderUserDashboard(role, sessionId, onLogout) {
    const appEl = document.getElementById("app");
    
    // Draw initial layout frame
    appEl.innerHTML = `
        <div class="dashboard-wrapper">
            ${renderSidebar(role, "overview")}
            <main class="dashboard-main">
                <header class="panel-header">
                    <h1 class="panel-title">User Command Center</h1>
                    <span style="font-family: var(--font-heading); color: var(--text-secondary);">
                         clearance: operator
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

    // Bind logout button action
    document.getElementById("btn-logout").addEventListener("click", () => {
        onLogout();
    });

    // Load data from backend
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
            
            // Render components dynamically
            const contentEl = document.getElementById("dashboard-content");
            contentEl.innerHTML = `
                <div class="grid-col">
                    ${renderSystemStatus(data.system_status, data.role)}
                    <div style="margin-top: 25px;"></div>
                    <div id="biometric-enrollment-container"></div>
                    <div style="margin-top: 25px;"></div>
                    ${renderDevicePanel(data.devices)}
                </div>
                <div class="grid-col">
                    ${renderEventStream(data.recent_events, data.alerts)}
                </div>
            `;
            
            if (data.person_id) {
                renderBiometricEnrollment("biometric-enrollment-container", data.person_id);
            }

        } catch (err) {
            document.getElementById("dashboard-content").innerHTML = `
                <div style="grid-column: span 2; text-align: center; color: var(--accent-danger); padding: 50px 0;">
                    ${err.message || "Failed to load telemetry."}
                </div>
            `;
        }
    }

    loadDashboardData();
    
    // Add Assistant Panel
    renderAssistantPanel(appEl, sessionId);
}

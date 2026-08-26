import { renderLoginPage } from "./pages/login.js";
import { renderUserDashboard } from "./pages/user_dashboard.js";
import { renderAdminDashboard } from "./pages/admin_dashboard.js";

console.log("[ATLAS FRONTEND] index.js loaded");

// Keep active session in memory and sync with localStorage for persistence
let activeSession = {
    token: localStorage.getItem("atlas_session_token") || null,
    role: localStorage.getItem("atlas_session_role") || null
};

export async function checkSession() {
    console.log("[ATLAS FRONTEND] checkSession started");
    if (!activeSession.token) {
        console.log("[ATLAS FRONTEND] no token, calling showLogin");
        showLogin();
        return;
    }

    try {
        const response = await fetch("/api/v1/auth/session", {
            headers: {
                "Authorization": `Bearer ${activeSession.token}`
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            showDashboard(data.role, activeSession.token);
        } else {
            clearSession();
            showLogin();
        }
    } catch (err) {
        clearSession();
        showLogin();
    }
}

function showLogin() {
    renderLoginPage((role, token) => {
        localStorage.setItem("atlas_session_token", token);
        localStorage.setItem("atlas_session_role", role);
        activeSession.token = token;
        activeSession.role = role;
        showDashboard(role, token);
    });
}

function showDashboard(role, token) {
    if (role.toUpperCase() === "ADMIN") {
        renderAdminDashboard(role, token, handleLogout);
    } else {
        renderUserDashboard(role, token, handleLogout);
    }
}

async function handleLogout() {
    if (activeSession.token) {
        try {
            await fetch("/api/v1/auth/logout", {
                method: "POST",
                headers: {
                    "Authorization": `Bearer ${activeSession.token}`
                }
            });
        } catch (e) {
            console.error("Logout API request failed:", e);
        }
    }
    clearSession();
    showLogin();
}

function clearSession() {
    localStorage.removeItem("atlas_session_token");
    localStorage.removeItem("atlas_session_role");
    activeSession.token = null;
    activeSession.role = null;
}

// Start router
checkSession();

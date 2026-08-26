import { renderBiometricVerification } from "../components/BiometricVerification.js";
import { requestLocation, buildLocationBadgeHtml } from "../services/locationService.js";

export function renderLoginPage(onLoginSuccess) {
    console.log("[ATLAS FRONTEND] renderLoginPage started");
    const html = `
        <div class="login-container">
            <div class="login-card glass-panel" id="login-card-content">
                <h1 class="brand-title">ATLAS OS</h1>
                <p class="brand-subtitle">Autonomous Control System</p>

                <form id="login-form">
                    <div class="form-group">
                        <label class="form-label" for="username">Operator Identification (ID)</label>
                        <input class="form-input" type="text" id="username" placeholder="Username" required autocomplete="username">
                    </div>
                    
                    <div class="form-group">
                        <label class="form-label" for="password">Security Access Key (Password)</label>
                        <input class="form-input" type="password" id="password" placeholder="••••••••" required autocomplete="current-password">
                    </div>

                    <button class="btn-primary" type="submit" id="btn-submit">
                        Verify &amp; Access
                    </button>
                </form>

                <div class="error-text" id="error-message" style="display: none;"></div>

                <div class="status-indicator">
                    <span class="status-dot"></span>System Status: Online
                </div>

                <!-- GPS location badge — updated after permission result is known -->
                <div class="loc-badge-container" id="loc-badge-container" aria-live="polite"></div>
            </div>
        </div>
    `;

    document.getElementById("app").innerHTML = html;

    const form        = document.getElementById("login-form");
    const submitBtn   = document.getElementById("btn-submit");
    const errMsg      = document.getElementById("error-message");
    const locBadge    = document.getElementById("loc-badge-container");

    /**
     * Sends the login API request.
     * gpsData — result from locationService.requestLocation(), may be null.
     * biometricToken — one-time verification token, optional.
     */
    const doLogin = async (username, password, biometricToken = null, gpsData = null) => {
        const payload = { username, password };
        if (biometricToken) {
            payload.biometric_input = biometricToken;
        }
        // Attach GPS only when we actually captured a location result
        if (gpsData) {
            payload.gps_location = {
                latitude:  gpsData.latitude,
                longitude: gpsData.longitude,
                accuracy:  gpsData.accuracy,
                timestamp: gpsData.timestamp,
                status:    gpsData.status,
            };
        }

        const response = await fetch("/api/v1/auth/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const rawText = await response.text();
        let data = {};
        if (rawText) {
            try {
                data = JSON.parse(rawText);
            } catch (error) {
                console.error("[LOGIN] Backend returned non-JSON response:", rawText);
                throw new Error(`Server returned an invalid response (HTTP ${response.status})`);
            }
        }
        return { ok: response.ok, data };
    };

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const username = document.getElementById("username").value;
        const password = document.getElementById("password").value;

        errMsg.style.display = "none";
        submitBtn.disabled = true;

        // Request GPS location — runs concurrently; login always proceeds regardless of result
        console.log("[LOCATION] Requesting browser GPS...");
        const locationData = await requestLocation();
        console.log("[LOCATION] Result:", locationData);

        // Update badge so the user knows what happened
        if (locBadge) {
            locBadge.innerHTML = buildLocationBadgeHtml(locationData);
        }

        try {
            const { ok, data } = await doLogin(username, password, null, locationData);

            if (ok && data.authenticated) {
                onLoginSuccess(data.role, data.session_id);

            } else if (!data.authenticated && data.biometric_required) {
                // Intercept and launch biometric gate — pass locationData through
                const card = document.getElementById("login-card-content");
                const originalHtml = card.innerHTML;

                card.innerHTML = `<div id="biometric-gate-container"></div>`;

                renderBiometricVerification(
                    "biometric-gate-container",
                    data.person_id,
                    username,
                    password,
                    locationData,           // pass captured GPS into biometric gate
                    async (token) => {
                        // Success: finish login with biometric token + same GPS data
                        try {
                            const result = await doLogin(username, password, token, locationData);
                            if (result.ok && result.data.authenticated) {
                                onLoginSuccess(result.data.role, result.data.session_id);
                            } else {
                                throw new Error("Final authentication failed after biometrics.");
                            }
                        } catch (err) {
                            card.innerHTML = originalHtml;
                            document.getElementById("error-message").innerText = err.message || "AUTHENTICATION FAILED";
                            document.getElementById("error-message").style.display = "block";
                            document.getElementById("btn-submit").disabled = false;
                        }
                    },
                    () => {
                        // Cancel: restore login form
                        card.innerHTML = originalHtml;
                        document.getElementById("btn-submit").disabled = false;
                        renderLoginPage(onLoginSuccess);
                    }
                );

            } else {
                throw new Error(data.message || "AUTHENTICATION FAILED");
            }
        } catch (err) {
            errMsg.innerText = err.message || "AUTHENTICATION FAILED";
            errMsg.style.display = "block";
            submitBtn.disabled = false;
        }
    });
}

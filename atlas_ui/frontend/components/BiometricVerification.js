import { BiometricService } from "../services/biometricService.js";
import { requestLocation, buildLocationBadgeHtml } from "../services/locationService.js";

/**
 * Renders the biometric verification gate inside containerId.
 *
 * @param {string}   containerId       - DOM element to render into
 * @param {string}   personId          - ATLAS person ID to verify against
 * @param {string}   username          - operator username (for biometric reset flow)
 * @param {string}   password          - operator password (for biometric reset flow)
 * @param {object|null} locationData   - GPS result from locationService (may be null)
 * @param {Function} onVerifySuccess   - called with the one-time verification token on success
 * @param {Function} onCancel          - called when the user cancels
 */
export function renderBiometricVerification(
    containerId,
    personId,
    username,
    password,
    locationData,
    onVerifySuccess,
    onCancel
) {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = `
        <div class="biometric-gate" style="text-align: center;">
            <h2 class="brand-subtitle" style="margin-bottom: 10px;">Identity Verification Required</h2>
            <p style="margin-bottom: 20px; color: var(--text-secondary);">
                Facial authentication is required to access this terminal.
            </p>
            
            <div id="video-container" style="display: none; margin-bottom: 20px;">
                <video id="biometric-video" autoplay playsinline style="width: 100%; max-width: 400px; border-radius: 8px; border: 2px solid var(--border-color); transform: rotate(90deg);"></video>
                <canvas id="biometric-canvas" style="display: none;"></canvas>
            </div>

            <div id="biometric-state-display" style="margin-bottom: 20px;">
                <div class="status-indicator">
                    <span class="status-dot"></span>Camera Offline
                </div>
            </div>
            <div class="error-text" id="biometric-error-message" style="display: none; margin-bottom: 20px;"></div>
            
            <!-- GPS location badge for biometric verification context -->
            <div class="loc-badge-container" id="biometric-loc-badge" aria-live="polite"></div>

            <div style="display: flex; gap: 10px; justify-content: center; margin-bottom: 10px; margin-top: 12px;">
                <button class="btn-primary" id="btn-verify-face">Verify Identity</button>
                <button class="btn-secondary" id="btn-cancel-verify">Cancel</button>
            </div>
            <div style="margin-top: 15px;">
                <a href="#" id="link-reset-biometrics" style="color: var(--text-secondary); font-size: 0.85rem; text-decoration: underline; cursor: pointer;">
                    Reset Biometric Profile
                </a>
            </div>
        </div>
    `;

    const btnVerify      = document.getElementById("btn-verify-face");
    const btnCancel      = document.getElementById("btn-cancel-verify");
    const errMsg         = document.getElementById("biometric-error-message");
    const stateDisplay   = document.getElementById("biometric-state-display");
    const video          = document.getElementById("biometric-video");
    const canvas         = document.getElementById("biometric-canvas");
    const videoContainer = document.getElementById("video-container");
    const linkReset      = document.getElementById("link-reset-biometrics");
    const locBadge       = document.getElementById("biometric-loc-badge");

    let stream      = null;
    let isVerifying = false;

    // ── Show GPS badge immediately using whatever data was passed in ──────────
    // If locationData was already resolved upstream (from the login form), use it.
    // If null, we'll request location fresh when verification starts.
    let activeLocationData = locationData || null;
    if (locBadge) {
        locBadge.innerHTML = buildLocationBadgeHtml(activeLocationData);
    }

    const stopCamera = () => {
        isVerifying = false;
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
    };

    btnCancel.addEventListener("click", () => {
        stopCamera();
        if (onCancel) onCancel();
    });

    if (linkReset) {
        linkReset.addEventListener("click", async (e) => {
            e.preventDefault();
            if (!confirm("Are you sure you want to reset your biometric profile? This will delete your current face templates and allow credentials-only access.")) {
                return;
            }

            stopCamera();
            stateDisplay.innerHTML = `
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--warning-color); box-shadow: 0 0 8px var(--warning-color);"></span>
                    Resetting biometric profile...
                </div>
            `;

            try {
                await BiometricService.reset(username, password);
                stateDisplay.innerHTML = `
                    <div class="status-indicator">
                        <span class="status-dot" style="background: var(--success-color); box-shadow: 0 0 8px var(--success-color);"></span>
                        Reset Successful!
                    </div>
                `;
                setTimeout(() => onVerifySuccess(null), 1500);
            } catch (err) {
                console.error(err);
                errMsg.innerText = err.message || "Failed to reset biometric profile.";
                errMsg.style.display = "block";
                stateDisplay.innerHTML = `
                    <div class="status-indicator">
                        <span class="status-dot" style="background: var(--error-color);"></span>
                        Reset Failed
                    </div>
                `;
            }
        });
    }

    const captureAndVerify = async () => {
        if (!isVerifying) return;

        const ctx = canvas.getContext("2d");
        if (video.videoWidth > 0 && video.videoHeight > 0) {
            // Rotate 90° to correct webcam orientation
            canvas.width  = video.videoHeight;
            canvas.height = video.videoWidth;
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.save();
            ctx.translate(canvas.width / 2, canvas.height / 2);
            ctx.rotate(90 * Math.PI / 180);
            ctx.drawImage(video, -video.videoWidth / 2, -video.videoHeight / 2, video.videoWidth, video.videoHeight);
            ctx.restore();

            const imageData = canvas.toDataURL("image/jpeg", 0.8);

            try {
                // Pass locationData to verify — attaches GPS to the server request
                const result = await BiometricService.verify(personId, imageData, activeLocationData);

                if (result.success && result.verified) {
                    stopCamera();
                    stateDisplay.innerHTML = `
                        <div class="status-indicator">
                            <span class="status-dot" style="background: var(--success-color); box-shadow: 0 0 8px var(--success-color);"></span>
                            Identity Verified
                        </div>
                    `;
                    setTimeout(() => onVerifySuccess(result.verification_token), 1000);
                    return; // Stop loop
                } else {
                    let userMsg = "Verification failed.";
                    if (result.reason === "NO_FACE")              userMsg = "No face was detected.";
                    else if (result.reason === "MULTIPLE_FACES")  userMsg = "Multiple faces detected.";
                    else if (result.reason === "QUALITY_REJECTED") userMsg = "Face quality insufficient.";
                    else if (result.reason === "RE_ENROLLMENT_REQUIRED") {
                        stopCamera();
                        errMsg.innerText = "Biometric profile is outdated. Please re-enroll.";
                        errMsg.style.display = "block";
                        btnVerify.disabled = false;
                        btnCancel.disabled = false;
                        return;
                    } else if (result.reason === "NOT_ENROLLED") {
                        stopCamera();
                        errMsg.innerText = "No biometric profile found.";
                        errMsg.style.display = "block";
                        btnVerify.disabled = false;
                        btnCancel.disabled = false;
                        return;
                    }

                    stateDisplay.innerHTML = `
                        <div class="status-indicator">
                            <span class="status-dot" style="background: var(--warning-color); box-shadow: 0 0 8px var(--warning-color);"></span>
                            ${userMsg} Retrying...
                        </div>
                    `;
                }
            } catch (err) {
                console.error(err);
                // Continue retrying on transient errors unless it's a hard fail
            }
        }

        // Loop
        if (isVerifying) {
            setTimeout(captureAndVerify, 1000);
        }
    };

    btnVerify.addEventListener("click", async () => {
        btnVerify.disabled = true;
        errMsg.style.display = "none";

        // If no GPS data was passed in, request it now (non-blocking; verification proceeds regardless)
        if (!activeLocationData) {
            console.log("[LOCATION] No prior GPS data — requesting at biometric gate...");
            activeLocationData = await requestLocation();
            console.log("[LOCATION] Biometric gate GPS result:", activeLocationData);
            if (locBadge) {
                locBadge.innerHTML = buildLocationBadgeHtml(activeLocationData);
            }
        }

        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true });
            video.srcObject = stream;
            videoContainer.style.display = "block";
            isVerifying = true;

            stateDisplay.innerHTML = `
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--primary-color); box-shadow: 0 0 8px var(--primary-color);"></span>
                    Please look at the camera...
                </div>
            `;

            // Start the verification loop
            setTimeout(captureAndVerify, 1000);
        } catch (err) {
            console.error(err);
            btnVerify.disabled = false;
            errMsg.innerText = "Camera access denied or unavailable.";
            errMsg.style.display = "block";

            stateDisplay.innerHTML = `
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--error-color);"></span>
                    Camera Error
                </div>
            `;
        }
    });
}

import { BiometricService } from "../services/biometricService.js";

export function renderBiometricEnrollment(containerId, personId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    let currentState = "IDLE";
    let statusData = null;
    let stream = null;
    let isEnrolling = false;

    const stopCamera = () => {
        isEnrolling = false;
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
            stream = null;
        }
    };

    const render = () => {
        let content = "";
        
        if (currentState === "CHECKING_STATUS" || currentState === "IDLE") {
            content = `
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--warning-color); box-shadow: 0 0 8px var(--warning-color);"></span>
                    Checking biometric profile...
                </div>
            `;
        } else if (currentState === "NOT_ENROLLED") {
            content = `
                <p style="margin-bottom: 15px;">No biometric profile found. Face authentication has not been configured.</p>
                <button class="btn-primary" id="btn-enroll-action">Enroll Face Now</button>
            `;
        } else if (currentState === "ENROLLED") {
            content = `
                <p style="margin-bottom: 15px; color: var(--success-color);">Face authentication successfully configured.</p>
                <p style="margin-bottom: 15px; font-size: 0.9em; color: var(--text-secondary);">
                    Templates: ${statusData?.template_count || 5} | Dimension: ${statusData?.embedding_dimension || 512}
                </p>
                <button class="btn-secondary" id="btn-enroll-action">Re-enroll Face</button>
            `;
        } else if (currentState === "ENROLLING") {
            content = `
                <div class="status-indicator" style="margin-bottom: 15px;">
                    <span class="status-dot" style="background: var(--warning-color); box-shadow: 0 0 8px var(--warning-color);"></span>
                    Capturing biometric samples...
                </div>
                
                <div id="video-container" style="margin-bottom: 20px;">
                    <video id="biometric-enroll-video" autoplay playsinline style="width: 100%; max-width: 400px; border-radius: 8px; border: 2px solid var(--border-color); transform: rotate(90deg);"></video>
                    <canvas id="biometric-enroll-canvas" style="display: none;"></canvas>
                </div>
                
                <div id="enroll-progress-display" style="margin-bottom: 15px; color: #00d0ff;">
                    Position face in camera...
                </div>

                <div class="error-text" style="display: none; margin-bottom: 15px;" id="enroll-error-msg"></div>
                <button class="btn-secondary" id="btn-cancel-enroll">Cancel</button>
            `;
        } else if (currentState === "ERROR") {
            content = `
                <div class="error-text" style="display: block; margin-bottom: 15px;" id="enroll-error-msg"></div>
                <button class="btn-primary" id="btn-enroll-action">Try Again</button>
            `;
        }

        container.innerHTML = `
            <div class="glass-panel" style="margin-bottom: 20px;">
                <h3 style="margin-bottom: 15px; font-weight: 600;">Biometric Authentication</h3>
                ${content}
            </div>
        `;

        const btnEnroll = document.getElementById("btn-enroll-action");
        if (btnEnroll) {
            btnEnroll.addEventListener("click", handleEnroll);
        }
        
        const btnCancel = document.getElementById("btn-cancel-enroll");
        if (btnCancel) {
            btnCancel.addEventListener("click", () => {
                stopCamera();
                loadStatus();
            });
        }
    };

    const loadStatus = async () => {
        currentState = "CHECKING_STATUS";
        render();
        try {
            const data = await BiometricService.getStatus(personId);
            statusData = data;
            if (data.enrolled) {
                currentState = "ENROLLED";
            } else {
                currentState = "NOT_ENROLLED";
            }
            render();
        } catch (e) {
            currentState = "ERROR";
            render();
            document.getElementById("enroll-error-msg").innerText = "Failed to load biometric status.";
        }
    };

    const handleEnroll = async () => {
        currentState = "ENROLLING";
        render();
        
        const video = document.getElementById("biometric-enroll-video");
        const canvas = document.getElementById("biometric-enroll-canvas");
        const progressDisplay = document.getElementById("enroll-progress-display");
        const errMsg = document.getElementById("enroll-error-msg");
        
        try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
            video.srcObject = stream;
            isEnrolling = true;
            
            // Wait for video to be ready
            video.onloadedmetadata = () => {
                video.play();
                captureLoop();
            };
        } catch (err) {
            currentState = "ERROR";
            render();
            document.getElementById("enroll-error-msg").innerText = "Camera access denied or unavailable.";
        }
        
        const captureLoop = async () => {
            if (!isEnrolling) return;
            
            const ctx = canvas.getContext("2d");
            if (video.videoWidth > 0 && video.videoHeight > 0) {
                // Swap canvas width/height for 90 degree rotation
                canvas.width = video.videoHeight;
                canvas.height = video.videoWidth;
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.save();
                ctx.translate(canvas.width / 2, canvas.height / 2);
                ctx.rotate(90 * Math.PI / 180); // Rotate 90 degrees clockwise to correct orientation
                ctx.drawImage(video, -video.videoWidth / 2, -video.videoHeight / 2, video.videoWidth, video.videoHeight);
                ctx.restore();
                
                const imageData = canvas.toDataURL("image/jpeg", 0.8);
                
                try {
                    const result = await BiometricService.enroll(personId, imageData);
                    if (result.success) {
                        stopCamera();
                        progressDisplay.innerText = "Enrollment complete";
                        progressDisplay.style.color = "#39ff14";
                        setTimeout(() => loadStatus(), 1500);
                        return;
                    } else if (result.error === "Collecting") {
                        progressDisplay.innerText = `Sample ${result.samples_captured} / ${result.samples_requested}`;
                        if (result.reason) {
                            errMsg.innerText = result.reason;
                            errMsg.style.display = "block";
                        } else {
                            errMsg.style.display = "none";
                        }
                    } else {
                        stopCamera();
                        currentState = "ERROR";
                        render();
                        let userMsg = result.message || result.reason || "Enrollment failed.";
                        if (result.reason === "CAMERA_BUSY") userMsg = "Another biometric operation is currently using the camera.";
                        document.getElementById("enroll-error-msg").innerText = userMsg;
                        return;
                    }
                } catch (e) {
                    // Just ignore network errors in loop and retry unless it's fatal
                }
            }
            
            if (isEnrolling) {
                setTimeout(captureLoop, 1000); // 1 FPS to collect 5 samples
            }
        };
    };

    // Initial load
    loadStatus();
}

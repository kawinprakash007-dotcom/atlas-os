export function renderVisionPanel(containerId, sessionId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // Local state
    let activeTracksCount = 0;
    let cachedStatus = null;
    let eventLog = [];

    // Draw frame
    container.innerHTML = `
        <div class="vision-panel-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; width: 100%;">
            <!-- Column 1: System Status & Diagnostics -->
            <div class="grid-col" style="display: flex; flex-direction: column; gap: 20px;">
                <!-- Section A: System Overview -->
                <div class="panel-card glass-panel">
                    <div class="card-title">ATLAS Vision Overview</div>
                    <div class="status-item">
                        <span>ATLAS OS Core</span>
                        <span id="vision-os-status" style="font-weight: bold; color: var(--text-muted);">CHECKING...</span>
                    </div>
                    <div class="status-item">
                        <span>ATLAS Vision Edge</span>
                        <span id="vision-edge-status" style="font-weight: bold; color: var(--text-muted);">CHECKING...</span>
                    </div>
                    <div class="status-item">
                        <span>OS ↔ Edge Connection</span>
                        <span id="vision-connection-status" style="font-weight: bold; color: var(--text-muted);">CHECKING...</span>
                    </div>
                    <div class="status-item">
                        <span>Last Update Sync</span>
                        <span id="vision-last-update" style="color: var(--text-secondary);">--</span>
                    </div>
                </div>

                <!-- Section B: Synchronization Metrics -->
                <div class="panel-card glass-panel">
                    <div class="card-title">Database & Sync Telemetry</div>
                    <div class="status-item">
                        <span>Identity Sync State</span>
                        <span id="sync-identity-state" style="font-weight: bold; color: var(--text-muted);">--</span>
                    </div>
                    <div class="status-item">
                        <span>Biometric Sync State</span>
                        <span id="sync-biometric-state" style="font-weight: bold; color: var(--text-muted);">--</span>
                    </div>
                    <div class="status-item">
                        <span>Edge Cache (Identities)</span>
                        <span id="sync-identity-cache" style="color: var(--accent-color); font-weight: bold;">--</span>
                    </div>
                    <div class="status-item">
                        <span>Edge Cache (Biometrics)</span>
                        <span id="sync-biometric-cache" style="color: var(--accent-color); font-weight: bold;">--</span>
                    </div>
                    <div class="status-item">
                        <span>Sync Retry Count</span>
                        <span id="sync-retry-count" style="color: var(--text-primary);">--</span>
                    </div>
                </div>

                <!-- Section D: Vision Pipeline Monitor (Real Camera stream) -->
                <div class="panel-card glass-panel">
                    <div class="card-title">Vision Pipeline Monitor</div>
                    <div style="position: relative; width: 100%; border-radius: 4px; overflow: hidden; background: rgba(0, 0, 0, 0.4); border: 1px solid rgba(255,255,255,0.1); margin-bottom: 15px;">
                        <img id="vision-camera-feed" style="width: 100%; height: auto; display: block; min-height: 240px; background: rgba(0,0,0,0.5);" alt="ATLAS Vision Live Feed" />
                        <div id="vision-camera-overlay" style="position: absolute; top: 10px; left: 10px; padding: 4px 8px; border-radius: 3px; font-weight: bold; font-size: 0.75rem; text-transform: uppercase;">
                            ● CHECKING...
                        </div>
                    </div>
                    <div class="status-item">
                        <span>Camera Connection</span>
                        <span id="camera-conn-state" style="font-weight: bold; color: var(--text-muted);">--</span>
                    </div>
                    <div class="status-item">
                        <span>Source Path</span>
                        <span id="camera-source-path" style="color: var(--text-secondary); font-family: monospace; font-size: 0.8rem;">--</span>
                    </div>
                    <div class="status-item">
                        <span>Resolution &amp; FPS</span>
                        <span id="camera-resolution-fps" style="color: var(--accent-color); font-weight: bold;">--</span>
                    </div>
                    <div class="status-item">
                        <span>Frames Received / Processed</span>
                        <span id="camera-frames-received-processed" style="color: var(--text-primary);">--</span>
                    </div>
                    <div class="status-item">
                        <span>Active Tracking Units</span>
                        <span id="pipeline-active-tracks" style="color: var(--accent-color); font-weight: bold;">0</span>
                    </div>
                    <div class="status-item">
                        <span>Dropped Recognition Tasks</span>
                        <span id="pipeline-dropped-tasks" style="color: var(--text-primary);">0</span>
                    </div>
                    <div class="status-item">
                        <span>Reconnect Actions Count</span>
                        <span id="camera-reconnect-count" style="color: var(--text-secondary);">0</span>
                    </div>
                </div>
            </div>

            <!-- Column 2: Event Feed & Simulation Controls -->
            <div class="grid-col" style="display: flex; flex-direction: column; gap: 20px;">
                <!-- Section C: Live Event Feed -->
                <div class="panel-card glass-panel" style="flex-grow: 1; display: flex; flex-direction: column; min-height: 380px;">
                    <div class="card-title">Live Biometric Event Feed</div>
                    <div id="vision-event-list" style="overflow-y: auto; flex-grow: 1; max-height: 320px; font-size: 0.85rem; padding-right: 5px;">
                        <div style="color: var(--text-muted); text-align: center; padding: 40px 0;">No Vision events captured in this session.</div>
                    </div>
                </div>

                <!-- Section E: Diagnostics & Simulation Controls -->
                <div class="panel-card glass-panel">
                    <div class="card-title" style="color: var(--accent-danger); border-bottom: 1px solid rgba(255, 7, 58, 0.2);">Vision Diagnostics &amp; Simulation</div>
                    
                    <div style="display: flex; flex-direction: column; gap: 15px; margin-top: 15px;">
                        <!-- Camera Controls -->
                        <div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid rgba(255, 255, 255, 0.05);">
                            <span style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; display: block; margin-bottom: 8px;">Hardware Camera Actions</span>
                            <div style="display: flex; gap: 10px;">
                                <button class="btn-primary" id="btn-camera-start" style="padding: 6px 15px; font-size: 0.8rem; background: #39ff14; color: black; border-color: #39ff14;">Start Camera</button>
                                <button class="btn-primary" id="btn-camera-stop" style="padding: 6px 15px; font-size: 0.8rem; background: #ff073a; color: white; border-color: #ff073a;">Stop Camera</button>
                            </div>
                            <div id="camera-action-status" style="font-size: 0.75rem; color: var(--text-muted); margin-top: 8px; text-transform: uppercase;">Ready</div>
                        </div>

                        <!-- Simulate Track -->
                        <div>
                            <span style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; display: block; margin-bottom: 5px;">Simulate Track Unit</span>
                            <div style="display: flex; gap: 10px;">
                                <input type="text" id="sim-track-id" class="form-input" style="padding: 6px 12px; margin: 0; font-size: 0.8rem; background: rgba(0,0,0,0.4);" placeholder="TRACK-0001" value="TRACK-0001">
                                <button class="btn-primary" id="btn-sim-track" style="padding: 6px 15px; font-size: 0.8rem; flex-shrink: 0;">Simulate Entry</button>
                            </div>
                        </div>

                        <!-- Simulate Match -->
                        <div>
                            <span style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; display: block; margin-bottom: 5px;">Simulate Biometric Recognition Match</span>
                            <div style="display: flex; flex-direction: column; gap: 8px;">
                                <div style="display: flex; gap: 10px;">
                                    <input type="text" id="sim-match-track" class="form-input" style="padding: 6px 12px; margin: 0; font-size: 0.8rem; background: rgba(0,0,0,0.4);" placeholder="TRACK-0001" value="TRACK-0001">
                                    <input type="text" id="sim-match-person" class="form-input" style="padding: 6px 12px; margin: 0; font-size: 0.8rem; background: rgba(0,0,0,0.4);" placeholder="ATLAS-P-88888888" value="ATLAS-P-88888888">
                                </div>
                                <button class="btn-primary" id="btn-sim-match" style="padding: 6px 15px; font-size: 0.8rem; align-self: flex-end;">Trigger Match</button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    // References
    const visionOsStatus = document.getElementById("vision-os-status");
    const visionEdgeStatus = document.getElementById("vision-edge-status");
    const visionConnection = document.getElementById("vision-connection-status");
    const visionLastUpdate = document.getElementById("vision-last-update");

    const syncIdentityState = document.getElementById("sync-identity-state");
    const syncBiometricState = document.getElementById("sync-biometric-state");
    const syncIdentityCache = document.getElementById("sync-identity-cache");
    const syncBiometricCache = document.getElementById("sync-biometric-cache");
    const syncRetryCount = document.getElementById("sync-retry-count");

    // Camera References
    const feedImg = document.getElementById("vision-camera-feed");
    const feedOverlay = document.getElementById("vision-camera-overlay");
    const cameraConnState = document.getElementById("camera-conn-state");
    const cameraSourcePath = document.getElementById("camera-source-path");
    const cameraResolutionFps = document.getElementById("camera-resolution-fps");
    const cameraFramesReceivedProcessed = document.getElementById("camera-frames-received-processed");
    const pipelineActiveTracks = document.getElementById("pipeline-active-tracks");
    const pipelineDroppedTasks = document.getElementById("pipeline-dropped-tasks");
    const cameraReconnectCount = document.getElementById("camera-reconnect-count");

    const btnCameraStart = document.getElementById("btn-camera-start");
    const btnCameraStop = document.getElementById("btn-camera-stop");
    const cameraActionStatus = document.getElementById("camera-action-status");

    // Simulator References
    const simTrackId = document.getElementById("sim-track-id");
    const simMatchTrack = document.getElementById("sim-match-track");
    const simMatchPerson = document.getElementById("sim-match-person");

    const btnSimTrack = document.getElementById("btn-sim-track");
    const btnSimMatch = document.getElementById("btn-sim-match");

    const visionEventList = document.getElementById("vision-event-list");

    // Formatter helpers
    function setBadge(el, text, type) {
        if (!el) return;
        el.innerText = text.toUpperCase();
        el.style.padding = "2px 6px";
        el.style.borderRadius = "3px";
        el.style.fontSize = "0.75rem";
        el.style.fontWeight = "bold";

        if (type === "green") {
            el.style.color = "#39ff14";
            el.style.background = "rgba(57, 255, 20, 0.1)";
            el.style.border = "1px solid rgba(57, 255, 20, 0.3)";
        } else if (type === "red") {
            el.style.color = "#ff073a";
            el.style.background = "rgba(255, 7, 58, 0.1)";
            el.style.border = "1px solid rgba(255, 7, 58, 0.3)";
        } else if (type === "yellow") {
            el.style.color = "#ffcc00";
            el.style.background = "rgba(255, 204, 0, 0.1)";
            el.style.border = "1px solid rgba(255, 204, 0, 0.3)";
        } else if (type === "blue") {
            el.style.color = "var(--accent-color)";
            el.style.background = "rgba(0, 240, 255, 0.1)";
            el.style.border = "1px solid rgba(0, 240, 255, 0.3)";
        } else {
            el.style.color = "var(--text-muted)";
            el.style.background = "rgba(255, 255, 255, 0.05)";
            el.style.border = "1px solid rgba(255, 255, 255, 0.1)";
        }
    }

    // Refresh telemetry
    async function refreshStatus() {
        try {
            const response = await fetch("/api/v1/admin/vision/status", {
                method: "GET",
                headers: { "Authorization": `Bearer ${sessionId}` }
            });

            if (response.status === 401) return;
            if (!response.ok) throw new Error("Failed response");

            const data = await response.json();
            cachedStatus = data;

            // OS Status
            setBadge(visionOsStatus, "ONLINE", "green");

            // Edge Node Status
            const edge = data.edge_node || {};
            if (edge.status === "healthy") {
                setBadge(visionEdgeStatus, "ONLINE", "green");
                setBadge(visionConnection, "CONNECTED", "green");
                syncIdentityCache.innerText = edge.identity_cache_size ?? "--";
                syncBiometricCache.innerText = edge.biometric_cache_size ?? "--";
                activeTracksCount = edge.active_tracks ?? 0;
            } else {
                setBadge(visionEdgeStatus, "OFFLINE", "red");
                setBadge(visionConnection, "DISCONNECTED", "red");
                syncIdentityCache.innerText = "--";
                syncBiometricCache.innerText = "--";
            }

            // Sync States
            const worker = data.sync_worker || {};
            if (worker.retry_count > 0 && edge.status !== "healthy") {
                setBadge(syncIdentityState, "RETRYING", "yellow");
                setBadge(syncBiometricState, "RETRYING", "yellow");
            } else {
                setBadge(syncIdentityState, worker.identity_dirty ? "DIRTY" : "CLEAN", worker.identity_dirty ? "yellow" : "green");
                setBadge(syncBiometricState, worker.biometric_dirty ? "DIRTY" : "CLEAN", worker.biometric_dirty ? "yellow" : "green");
            }
            syncRetryCount.innerText = worker.retry_count ?? "0";
            visionLastUpdate.innerText = new Date().toLocaleTimeString();

        } catch (e) {
            setBadge(visionOsStatus, "OFFLINE", "red");
            setBadge(visionEdgeStatus, "UNAVAILABLE", "red");
            setBadge(visionConnection, "DISCONNECTED", "red");
            
            setBadge(syncIdentityState, "UNAVAILABLE", "grey");
            setBadge(syncBiometricState, "UNAVAILABLE", "grey");
            syncIdentityCache.innerText = "--";
            syncBiometricCache.innerText = "--";
            syncRetryCount.innerText = "--";
        }

        // Fetch Camera Status
        try {
            const response = await fetch("/api/v1/admin/vision/camera/status", {
                method: "GET",
                headers: { "Authorization": `Bearer ${sessionId}` }
            });

            if (!response.ok) throw new Error("Offline");

            const cam = await response.json();
            if (cam.status === "connected") {
                setBadge(cameraConnState, "CONNECTED", "green");
                
                // Redact credentials in URL if it is DroidCam
                let pathStr = cam.source || "--";
                if (pathStr.includes("@")) {
                    pathStr = "http://***:***@" + pathStr.split("@")[1];
                }
                cameraSourcePath.innerText = pathStr;
                cameraResolutionFps.innerText = `${cam.width}x${cam.height} @ ${cam.fps} FPS`;
                cameraFramesReceivedProcessed.innerText = `${cam.frames_received} / ${cam.frames_processed}`;
                pipelineActiveTracks.innerText = cam.active_tracks ?? "0";
                pipelineDroppedTasks.innerText = cam.dropped_rec_tasks ?? "0";
                cameraReconnectCount.innerText = cam.reconnect_count ?? "0";
                
                // Start polling frame when connected
                startFramePolling();
            } else {
                setBadge(cameraConnState, "DISCONNECTED", "red");
                cameraSourcePath.innerText = cam.source || "--";
                cameraResolutionFps.innerText = "--";
                cameraFramesReceivedProcessed.innerText = "--";
                pipelineActiveTracks.innerText = "0";
                pipelineDroppedTasks.innerText = cam.dropped_rec_tasks ?? "0";
                cameraReconnectCount.innerText = cam.reconnect_count ?? "0";
                
                // Stop polling frame when disconnected
                stopFramePolling();
            }
        } catch (e) {
            setBadge(cameraConnState, "UNAVAILABLE", "red");
            cameraSourcePath.innerText = "--";
            cameraResolutionFps.innerText = "--";
            cameraFramesReceivedProcessed.innerText = "--";
            pipelineActiveTracks.innerText = "0";
            pipelineDroppedTasks.innerText = "0";
            cameraReconnectCount.innerText = "0";
            
            // Stop polling frame on error
            stopFramePolling();
        }
    }

    // Video Stream continuous fetch
    let frameInterval = null;
    let activeFrameFetch = false;
    let consecutiveFrameFailures = 0;

    function updateFrame() {
        if (activeFrameFetch) return;
        activeFrameFetch = true;

        fetch("/api/v1/admin/vision/camera/frame", {
            headers: { "Authorization": `Bearer ${sessionId}` }
        })
        .then(res => {
            if (!res.ok) {
                if (res.status === 503) {
                    throw new Error("NoFrameYet");
                }
                throw new Error("Offline");
            }
            return res.blob();
        })
        .then(blob => {
            consecutiveFrameFailures = 0;
            const objectUrl = URL.createObjectURL(blob);
            const oldUrl = feedImg.src;
            feedImg.src = objectUrl;
            if (oldUrl && oldUrl.startsWith("blob:")) {
                URL.revokeObjectURL(oldUrl);
            }
            feedOverlay.innerText = "● STREAMING";
            feedOverlay.style.color = "#39ff14";
            feedOverlay.style.background = "rgba(57, 255, 20, 0.15)";
            feedOverlay.style.border = "1px solid rgba(57, 255, 20, 0.4)";
        })
        .catch(err => {
            consecutiveFrameFailures++;
            if (err.message === "NoFrameYet") {
                feedOverlay.innerText = "● STARTING";
                feedOverlay.style.color = "#ffcc00";
                feedOverlay.style.background = "rgba(255, 204, 0, 0.15)";
                feedOverlay.style.border = "1px solid rgba(255, 204, 0, 0.4)";
            } else {
                feedOverlay.innerText = "● OFFLINE";
                feedOverlay.style.color = "#ff073a";
                feedOverlay.style.background = "rgba(255, 7, 58, 0.15)";
                feedOverlay.style.border = "1px solid rgba(255, 7, 58, 0.4)";
                
                // Clear feed image on real failures
                feedImg.src = "";
                
                // Prevent hammering: stop polling if we have multiple consecutive failures
                if (consecutiveFrameFailures >= 3) {
                    console.warn("[VisionPanel] Stopping frame polling due to consecutive failures.");
                    stopFramePolling();
                }
            }
        })
        .finally(() => {
            activeFrameFetch = false;
        });
    }

    function startFramePolling() {
        if (frameInterval === null) {
            consecutiveFrameFailures = 0;
            frameInterval = setInterval(updateFrame, 160);
            console.log("[VisionPanel] Frame polling started.");
        }
    }

    function stopFramePolling() {
        if (frameInterval !== null) {
            clearInterval(frameInterval);
            frameInterval = null;
            console.log("[VisionPanel] Frame polling stopped.");
        }
    }

    // Camera actions Start/Stop
    btnCameraStart.addEventListener("click", async () => {
        btnCameraStart.disabled = true;
        cameraActionStatus.innerText = "Starting...";
        feedOverlay.innerText = "● CONNECTING";
        feedOverlay.style.color = "#ffcc00";
        feedOverlay.style.background = "rgba(255, 204, 0, 0.15)";
        feedOverlay.style.border = "1px solid rgba(255, 204, 0, 0.4)";
        try {
            const response = await fetch("/api/v1/admin/vision/camera/start", {
                method: "POST",
                headers: { "Authorization": `Bearer ${sessionId}` }
            });
            if (!response.ok) throw new Error("Failed");
            cameraActionStatus.innerText = "Start command enqueued successfully.";
            
            // Wait for backend confirmation
            await refreshStatus();
            startFramePolling();
        } catch(e) {
            cameraActionStatus.innerText = "Failed to start camera.";
            feedOverlay.innerText = "● FAILED";
            feedOverlay.style.color = "#ff073a";
            feedOverlay.style.background = "rgba(255, 7, 58, 0.15)";
            feedOverlay.style.border = "1px solid rgba(255, 7, 58, 0.4)";
        } finally {
            btnCameraStart.disabled = false;
        }
    });

    btnCameraStop.addEventListener("click", async () => {
        btnCameraStop.disabled = true;
        cameraActionStatus.innerText = "Stopping...";
        stopFramePolling();
        
        feedOverlay.innerText = "● OFFLINE";
        feedOverlay.style.color = "#ff073a";
        feedOverlay.style.background = "rgba(255, 7, 58, 0.15)";
        feedOverlay.style.border = "1px solid rgba(255, 7, 58, 0.4)";
        const oldUrl = feedImg.src;
        feedImg.src = "";
        if (oldUrl && oldUrl.startsWith("blob:")) {
            URL.revokeObjectURL(oldUrl);
        }

        try {
            const response = await fetch("/api/v1/admin/vision/camera/stop", {
                method: "POST",
                headers: { "Authorization": `Bearer ${sessionId}` }
            });
            if (!response.ok) throw new Error("Failed");
            cameraActionStatus.innerText = "Stop command executed successfully.";
            await refreshStatus();
        } catch(e) {
            cameraActionStatus.innerText = "Failed to stop camera.";
        } finally {
            btnCameraStop.disabled = false;
        }
    });

    // Event rendering helper
    function renderEvents() {
        if (eventLog.length === 0) {
            visionEventList.innerHTML = `<div style="color: var(--text-muted); text-align: center; padding: 40px 0;">No Vision events captured in this session.</div>`;
            return;
        }

        visionEventList.innerHTML = eventLog.map(e => {
            const timeStr = new Date(e.timestamp * 1000).toLocaleTimeString();
            let labelHtml = "";
            let detailsHtml = "";

            if (e.event_type === "PERSON_ENTERED") {
                labelHtml = `<span style="color: var(--accent-color); font-weight:bold;">[ENTRY]</span>`;
                detailsHtml = `Tracking unit <strong>${e.track_id}</strong> entered monitor frame.`;
            } else if (e.event_type === "PERSON_IDENTIFIED") {
                labelHtml = `<span style="color: #39ff14; font-weight:bold;">[RECOGNIZED]</span>`;
                
                const isAuthoritative = e.person_id && !e.person_id.startsWith("TRACK-");
                if (isAuthoritative) {
                    detailsHtml = `Resolved track <strong>${e.track_id}</strong> to identity <strong>${e.person_id}</strong> (${e.name || "Administrator"}). Confidence: ${(e.confidence * 100).toFixed(0)}%.`;
                } else {
                    detailsHtml = `<span style="color: var(--accent-danger);">Security Alert: Unresolved identity mapped to track ${e.track_id}.</span>`;
                }
            } else {
                labelHtml = `<span style="color: var(--text-muted);">[EVENT]</span>`;
                detailsHtml = `Event ${e.event_type} received.`;
            }

            return `
                <div class="event-item" style="padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.05); display: flex; flex-direction: column; gap: 4px;">
                    <div class="event-meta" style="display:flex; justify-content: space-between; font-size:0.75rem; color: var(--text-secondary);">
                        ${labelHtml}
                        <span>${timeStr}</span>
                    </div>
                    <div class="event-details">${detailsHtml}</div>
                </div>
            `;
        }).join("");

        visionEventList.scrollTop = 0;
    }

    // Add new event
    function addEvent(evt) {
        eventLog.unshift({
            event_type: evt.event_type || "UNKNOWN",
            track_id: evt.payload?.track_id || evt.track_id || "UNKNOWN",
            person_id: evt.payload?.person_id || evt.person_id || null,
            name: evt.payload?.name || evt.name || null,
            confidence: evt.payload?.confidence || evt.confidence || 0.0,
            timestamp: evt.timestamp || (Date.now() / 1000)
        });
        if (eventLog.length > 50) eventLog.pop();
        renderEvents();
    }

    // Simulation triggers
    btnSimTrack.addEventListener("click", async () => {
        const id = simTrackId.value.trim();
        if (!id) return;
        
        btnSimTrack.disabled = true;
        try {
            const response = await fetch(`/api/v1/admin/vision/test_track?track_id=${encodeURIComponent(id)}`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${sessionId}` }
            });
            if (!response.ok) throw new Error("Sim failed");
            simTrackId.value = `TRACK-${(parseInt(id.replace("TRACK-", "")) + 1).toString().padStart(4, "0")}`;
        } catch (e) {
            alert("Diagnostics offline: Cannot trigger simulation.");
        } finally {
            btnSimTrack.disabled = false;
            refreshStatus();
        }
    });

    btnSimMatch.addEventListener("click", async () => {
        const track = simMatchTrack.value.trim();
        const person = simMatchPerson.value.trim();
        if (!track || !person) return;

        btnSimMatch.disabled = true;
        try {
            const response = await fetch(`/api/v1/admin/vision/test_recognition?track_id=${encodeURIComponent(track)}&authoritative_id=${encodeURIComponent(person)}`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${sessionId}` }
            });
            if (!response.ok) throw new Error("Sim failed");
            const data = await response.json();
            if (data.status === "ignored_or_unauthorized") {
                alert("Sim match ignored: Ensure user is enrolled, enabled, and matches.");
            }
        } catch (e) {
            alert("Diagnostics offline: Cannot trigger simulation.");
        } finally {
            btnSimMatch.disabled = false;
            refreshStatus();
        }
    });

    // Custom Event Listener for WS updates
    const handleSystemEvent = (e) => {
        const payload = e.detail || {};
        if (payload.event_type === "PERSON_ENTERED" || payload.event_type === "PERSON_IDENTIFIED") {
            addEvent(payload);
        }
    };
    document.addEventListener("atlas-system-event", handleSystemEvent);

    // Initial load and periodic status polling
    refreshStatus();
    const pollInterval = setInterval(refreshStatus, 4000);

    // Return cleanup callback on unmount
    return () => {
        clearInterval(pollInterval);
        stopFramePolling();
        document.removeEventListener("atlas-system-event", handleSystemEvent);
    };
}

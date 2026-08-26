import { BiometricService } from "../services/biometricService.js";

export function renderUserManagement(containerId, sessionId, onRefreshDashboard) {
    const container = document.getElementById(containerId);
    if (!container) return;

    let users = [];
    
    // State variables for filtering and sorting
    let state = {
        searchQuery: "",
        roleFilter: "ALL",
        statusFilter: "ALL",
        bioFilter: "ALL",
        onlineFilter: "ALL",
        sortColumn: "username",
        sortDirection: "asc" // "asc" or "desc"
    };

    const loadUsers = async () => {
        try {
            container.innerHTML = `<div style="text-align:center; padding:50px; color:var(--accent-color);">LOADING USER DATA...</div>`;
            const response = await fetch("/api/v1/admin/users", {
                headers: { "Authorization": `Bearer ${sessionId}` }
            });
            if (!response.ok) throw new Error("Failed to load users");
            const data = await response.json();
            users = data.users || [];
            renderUI();
        } catch (e) {
            container.innerHTML = `<div class="error-text">Failed to load user management: ${e.message}</div>`;
        }
    };

    const toggleStatus = async (accountId, enable) => {
        try {
            const res = await fetch(`/api/v1/admin/users/${accountId}/status`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${sessionId}`
                },
                body: JSON.stringify({ enabled: enable })
            });
            if (res.ok) {
                await loadUsers();
            } else {
                alert("Failed to update status");
            }
        } catch (e) {
            alert(e.message);
        }
    };
    
    const enrollFace = (personId) => {
        const modal = document.createElement("div");
        modal.className = "biometric-modal-overlay";
        modal.innerHTML = `
            <div class="biometric-modal-content glass-panel" style="width: 500px; text-align: center;">
                <h3 style="margin-bottom: 20px;">Biometric Enrollment</h3>
                <div id="enroll-video-container" style="margin-bottom: 20px;">
                    <video id="modal-enroll-video" autoplay playsinline style="width: 100%; max-width: 400px; border-radius: 8px; border: 2px solid var(--border-color); transform: rotate(90deg);"></video>
                    <canvas id="modal-enroll-canvas" style="display: none;"></canvas>
                </div>
                <div id="modal-enroll-progress" style="margin-bottom: 15px; color: #00d0ff;">
                    Position face in camera...
                </div>
                <div class="error-text" style="display: none; margin-bottom: 15px;" id="modal-enroll-error"></div>
                <div style="display: flex; gap: 10px; justify-content: center;">
                    <button class="btn-secondary" id="btn-modal-cancel">Cancel</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
        
        const video = document.getElementById("modal-enroll-video");
        const canvas = document.getElementById("modal-enroll-canvas");
        const progress = document.getElementById("modal-enroll-progress");
        const errMsg = document.getElementById("modal-enroll-error");
        const btnCancel = document.getElementById("btn-modal-cancel");
        
        let stream = null;
        let isEnrolling = true;
        
        const stopCamera = () => {
            isEnrolling = false;
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
                stream = null;
            }
        };
        
        btnCancel.addEventListener("click", () => {
            stopCamera();
            modal.remove();
        });
        
        const startEnrollment = async () => {
            try {
                stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
                video.srcObject = stream;
                
                video.onloadedmetadata = () => {
                    video.play();
                    captureLoop();
                };
            } catch (err) {
                errMsg.innerText = "Camera access denied.";
                errMsg.style.display = "block";
            }
        };
        
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
                        progress.innerText = "Enrollment Complete!";
                        progress.style.color = "#39ff14";
                        setTimeout(() => {
                            modal.remove();
                            loadUsers();
                        }, 1500);
                        return;
                    } else if (result.error === "Collecting") {
                        progress.innerText = `Sample ${result.samples_captured} / ${result.samples_requested}`;
                        if (result.reason) {
                            errMsg.innerText = result.reason;
                            errMsg.style.display = "block";
                        } else {
                            errMsg.style.display = "none";
                        }
                    } else {
                        stopCamera();
                        errMsg.innerText = result.message || result.reason || "Enrollment failed.";
                        errMsg.style.display = "block";
                        return;
                    }
                } catch (e) {
                    // ignore network errors in loop
                }
            }
            
            if (isEnrolling) {
                setTimeout(captureLoop, 1000);
            }
        };
        
        startEnrollment();
    };

    const handleSort = (column) => {
        if (state.sortColumn === column) {
            state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        } else {
            state.sortColumn = column;
            state.sortDirection = "asc";
        }
        renderUI();
    };

    const getFilteredAndSortedUsers = () => {
        let filtered = users.filter(u => {
            // Search
            const q = state.searchQuery.toLowerCase();
            const matchesSearch = q === "" || 
                (u.username && u.username.toLowerCase().includes(q)) ||
                (u.display_name && u.display_name.toLowerCase().includes(q)) ||
                (u.atlas_person_id && u.atlas_person_id.toLowerCase().includes(q));

            // Filters
            const matchesRole = state.roleFilter === "ALL" || u.role === state.roleFilter;
            const matchesStatus = state.statusFilter === "ALL" || 
                (state.statusFilter === "ACTIVE" && u.enabled) || 
                (state.statusFilter === "DISABLED" && !u.enabled);
            const matchesBio = state.bioFilter === "ALL" || u.face_enrollment_status === state.bioFilter;
            const matchesOnline = state.onlineFilter === "ALL" || 
                (state.onlineFilter === "ONLINE" && u.online) || 
                (state.onlineFilter === "OFFLINE" && !u.online);

            return matchesSearch && matchesRole && matchesStatus && matchesBio && matchesOnline;
        });

        // Sorting
        filtered.sort((a, b) => {
            let valA = a[state.sortColumn] || "";
            let valB = b[state.sortColumn] || "";

            // Handle specific derived or nested fields
            if (state.sortColumn === "name") {
                valA = a.display_name || "";
                valB = b.display_name || "";
            } else if (state.sortColumn === "last_access") {
                valA = a.last_access_timestamp || 0;
                valB = b.last_access_timestamp || 0;
            }

            if (typeof valA === "string") valA = valA.toLowerCase();
            if (typeof valB === "string") valB = valB.toLowerCase();

            if (valA < valB) return state.sortDirection === "asc" ? -1 : 1;
            if (valA > valB) return state.sortDirection === "asc" ? 1 : -1;
            return 0;
        });

        return filtered;
    };

    const formatDate = (ts) => {
        if (!ts) return "Never";
        return new Date(ts * 1000).toLocaleString();
    };

    const renderUI = () => {
        const displayedUsers = getFilteredAndSortedUsers();

        const rows = displayedUsers.map(u => {
            // Profile Image Logic (using generic icon to avoid heavy N+1 queries in table)
            let profileImgHtml = `<div style="width: 40px; height: 40px; border-radius: 50%; background: var(--bg-color); display: flex; align-items: center; justify-content: center; font-size: 18px; color: var(--text-secondary); border: 1px solid var(--border-color);"><i class="fas fa-user"></i></div>`;

            // Location Logic
            let locationHtml = "Unknown";
            if (u.gps_latitude && u.gps_longitude) {
                locationHtml = `<a href="https://maps.google.com/?q=${u.gps_latitude},${u.gps_longitude}" target="_blank" style="color: var(--accent-color); text-decoration: none;"><i class="fas fa-map-marker-alt"></i> ${u.gps_latitude.toFixed(4)}, ${u.gps_longitude.toFixed(4)}</a>`;
            }

            // Risk Indicator
            let riskLevel = u.risk_level || "LOW";
            let riskClass = "success";
            if (riskLevel === "HIGH") {
                riskClass = "danger";
            } else if (riskLevel === "MEDIUM") {
                riskClass = "warning";
            }
            let riskTooltip = (u.risk_reasons || ["No data"]).join("&#10;");

            return `
                <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.2s;">
                    <td style="padding: 15px 10px;">
                        <div style="display: flex; align-items: center; gap: 15px;">
                            ${profileImgHtml}
                            <div>
                                <div style="font-weight: bold; color: var(--text-primary);">${u.display_name || 'Unknown'}</div>
                                <div style="font-size: 0.85em; color: var(--text-secondary);">@${u.username}</div>
                            </div>
                        </div>
                    </td>
                    <td style="padding: 15px 10px; font-family: monospace; font-size: 0.9em; color: var(--text-secondary);">${u.atlas_person_id || 'N/A'}</td>
                    <td style="padding: 15px 10px;"><span class="status-badge" style="background: rgba(255,255,255,0.1);">${u.role}</span></td>
                    <td style="padding: 15px 10px;">
                        <span class="status-badge ${u.enabled ? 'success' : 'danger'}">${u.enabled ? 'ACTIVE' : 'DISABLED'}</span>
                    </td>
                    <td style="padding: 15px 10px;">
                        <span class="status-badge ${u.face_enrollment_status === 'ENROLLED' ? 'success' : (u.face_enrollment_status === 'FAILED' ? 'danger' : 'warning')}">${u.face_enrollment_status}</span>
                    </td>
                    <td style="padding: 15px 10px;">
                        ${u.online 
                            ? '<span style="color:var(--success-color); font-weight: bold;"><i class="fas fa-circle" style="font-size: 0.7em; margin-right: 5px; text-shadow: 0 0 5px var(--success-color);"></i>Online</span>' 
                            : '<span style="color:var(--text-secondary);"><i class="far fa-circle" style="font-size: 0.7em; margin-right: 5px;"></i>Offline</span>'}
                    </td>
                    <td style="padding: 15px 10px; font-size: 0.9em; color: var(--text-secondary);">
                        ${formatDate(u.last_access_timestamp || u.last_login)}
                    </td>
                    <td style="padding: 15px 10px; font-size: 0.9em;">${locationHtml}</td>
                    <td style="padding: 15px 10px;">
                        <span class="status-badge ${riskClass}" title="${riskTooltip}">${riskLevel}</span>
                    </td>
                    <td style="padding: 15px 10px;">
                        <div style="position: relative;">
                            <button class="btn-secondary btn-sm dropdown-btn" onclick="window.toggleUserDropdown('${u.account_id}')" style="width: 100px;">
                                ACTIONS ▼
                            </button>
                            <div id="dropdown-${u.account_id}" class="action-dropdown" style="display: none; position: absolute; top: 100%; right: 0; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: 4px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); z-index: 100; min-width: 200px; text-align: left; padding: 5px 0;">
                                <a href="#" style="display: block; padding: 8px 15px; color: var(--text-primary); text-decoration: none; font-size: 0.9em; transition: background 0.2s;" onclick="event.preventDefault(); window.viewUserDetails('${u.atlas_person_id}'); window.toggleUserDropdown('${u.account_id}');">
                                    <i class="fas fa-eye" style="width: 20px; text-align: center; margin-right: 5px;"></i> View Details
                                </a>
                                <a href="#" style="display: block; padding: 8px 15px; color: var(--text-primary); text-decoration: none; font-size: 0.9em; transition: background 0.2s;" onclick="event.preventDefault(); window.openEditUserModal('${u.account_id}', '${u.atlas_person_id}', '${u.username.replace(/'/g, "\\'")}', '${(u.display_name||'').replace(/'/g, "\\'")}', '${u.role}', ${u.enabled}); window.toggleUserDropdown('${u.account_id}');">
                                    <i class="fas fa-edit" style="width: 20px; text-align: center; margin-right: 5px;"></i> Edit User
                                </a>
                                <a href="#" style="display: block; padding: 8px 15px; color: var(--text-primary); text-decoration: none; font-size: 0.9em; transition: background 0.2s;" onclick="event.preventDefault(); window.openChangePasswordModal('${u.account_id}', '${u.username.replace(/'/g, "\\'")}', '${(u.display_name||'').replace(/'/g, "\\'")}', '${u.atlas_person_id}'); window.toggleUserDropdown('${u.account_id}');">
                                    <i class="fas fa-key" style="width: 20px; text-align: center; margin-right: 5px;"></i> Change Password
                                </a>
                                <a href="#" style="display: block; padding: 8px 15px; color: var(--text-primary); text-decoration: none; font-size: 0.9em; transition: background 0.2s;" onclick="event.preventDefault(); window.toggleUserStatus('${u.account_id}', ${!u.enabled}); window.toggleUserDropdown('${u.account_id}');">
                                    <i class="fas ${u.enabled ? 'fa-user-slash' : 'fa-user-check'}" style="width: 20px; text-align: center; margin-right: 5px;"></i> ${u.enabled ? 'Disable' : 'Enable'} Account
                                </a>
                                ${u.atlas_person_id ? `
                                <a href="#" style="display: block; padding: 8px 15px; color: var(--text-primary); text-decoration: none; font-size: 0.9em; transition: background 0.2s;" onclick="event.preventDefault(); window.enrollUserFace('${u.atlas_person_id}'); window.toggleUserDropdown('${u.account_id}');">
                                    <i class="fas fa-camera" style="width: 20px; text-align: center; margin-right: 5px;"></i> Enroll Face
                                </a>
                                <a href="#" style="display: block; padding: 8px 15px; color: var(--accent-danger); text-decoration: none; font-size: 0.9em; transition: background 0.2s;" onclick="event.preventDefault(); window.confirmResetBiometrics('${u.atlas_person_id}', '${u.username.replace(/'/g, "\\'")}'); window.toggleUserDropdown('${u.account_id}');">
                                    <i class="fas fa-undo" style="width: 20px; text-align: center; margin-right: 5px;"></i> Reset Biometrics
                                </a>
                                ` : ''}
                                <a href="#" style="display: block; padding: 8px 15px; color: var(--accent-danger); text-decoration: none; font-size: 0.9em; border-top: 1px solid var(--border-color); margin-top: 5px; transition: background 0.2s;" onclick="event.preventDefault(); window.confirmDeleteUser('${u.account_id}', '${u.username.replace(/'/g, "\\'")}'); window.toggleUserDropdown('${u.account_id}');">
                                    <i class="fas fa-trash-alt" style="width: 20px; text-align: center; margin-right: 5px;"></i> Delete User
                                </a>
                            </div>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");

        const getSortIcon = (col) => {
            if (state.sortColumn === col) {
                return state.sortDirection === "asc" ? '<i class="fas fa-sort-up"></i>' : '<i class="fas fa-sort-down"></i>';
            }
            return '<i class="fas fa-sort" style="opacity: 0.3;"></i>';
        };

        container.innerHTML = `
            <div class="glass-panel" style="padding: 25px; margin-bottom: 30px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                    <h2 class="card-title" style="margin: 0; display: flex; align-items: center; gap: 10px;">
                        <i class="fas fa-users" style="color: var(--accent-color);"></i> User Management
                    </h2>
                    <div style="display: flex; gap: 10px;">
                        <button class="btn-primary btn-sm" id="btn-create-user">
                            <i class="fas fa-plus"></i> CREATE USER
                        </button>
                        <button class="btn-secondary btn-sm" id="btn-refresh-users">
                            <i class="fas fa-sync-alt"></i> Refresh
                        </button>
                    </div>
                </div>

                <!-- Controls Bar -->
                <div style="display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 25px; padding: 15px; background: rgba(0, 0, 0, 0.2); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="flex: 1; min-width: 250px;">
                        <input type="text" id="um-search" placeholder="Search by name, username, or ID..." value="${state.searchQuery}" class="input-field" style="width: 100%; padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px;" />
                    </div>
                    <select id="um-filter-role" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${state.roleFilter === 'ALL' ? 'selected' : ''}>All Roles</option>
                        <option value="ADMIN" ${state.roleFilter === 'ADMIN' ? 'selected' : ''}>Admin</option>
                        <option value="USER" ${state.roleFilter === 'USER' ? 'selected' : ''}>User</option>
                    </select>
                    <select id="um-filter-status" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${state.statusFilter === 'ALL' ? 'selected' : ''}>All Status</option>
                        <option value="ACTIVE" ${state.statusFilter === 'ACTIVE' ? 'selected' : ''}>Active</option>
                        <option value="DISABLED" ${state.statusFilter === 'DISABLED' ? 'selected' : ''}>Disabled</option>
                    </select>
                    <select id="um-filter-bio" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${state.bioFilter === 'ALL' ? 'selected' : ''}>All Biometrics</option>
                        <option value="ENROLLED" ${state.bioFilter === 'ENROLLED' ? 'selected' : ''}>Enrolled</option>
                        <option value="NOT_ENROLLED" ${state.bioFilter === 'NOT_ENROLLED' ? 'selected' : ''}>Not Enrolled</option>
                    </select>
                    <select id="um-filter-online" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${state.onlineFilter === 'ALL' ? 'selected' : ''}>Any Connection</option>
                        <option value="ONLINE" ${state.onlineFilter === 'ONLINE' ? 'selected' : ''}>Online</option>
                        <option value="OFFLINE" ${state.onlineFilter === 'OFFLINE' ? 'selected' : ''}>Offline</option>
                    </select>
                </div>

                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; text-align: left; min-width: 1000px;">
                        <thead>
                            <tr style="border-bottom: 2px solid var(--border-color); color: var(--text-secondary);">
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('name')">User ${getSortIcon('name')}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('atlas_person_id')">Person ID ${getSortIcon('atlas_person_id')}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('role')">Role ${getSortIcon('role')}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('enabled')">Account Status ${getSortIcon('enabled')}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('face_enrollment_status')">Biometrics ${getSortIcon('face_enrollment_status')}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('online')">Session ${getSortIcon('online')}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('last_access')">Last Access ${getSortIcon('last_access')}</th>
                                <th style="padding: 12px 10px;">Last Location</th>
                                <th style="padding: 12px 10px;">Risk Level</th>
                                <th style="padding: 12px 10px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${rows.length > 0 ? rows : '<tr><td colspan="10" style="text-align: center; padding: 30px; color: var(--text-secondary);">No users found matching criteria.</td></tr>'}
                        </tbody>
                    </table>
                </div>
                <div style="margin-top: 15px; font-size: 0.85em; color: var(--text-secondary); text-align: right;">
                    Showing ${displayedUsers.length} of ${users.length} total users
                </div>
            </div>
        `;

        // Attach Event Listeners
        document.getElementById("um-search").addEventListener("input", (e) => {
            state.searchQuery = e.target.value;
            renderUI();
        });
        document.getElementById("um-filter-role").addEventListener("change", (e) => {
            state.roleFilter = e.target.value;
            renderUI();
        });
        document.getElementById("um-filter-status").addEventListener("change", (e) => {
            state.statusFilter = e.target.value;
            renderUI();
        });
        document.getElementById("um-filter-bio").addEventListener("change", (e) => {
            state.bioFilter = e.target.value;
            renderUI();
        });
        document.getElementById("um-filter-online").addEventListener("change", (e) => {
            state.onlineFilter = e.target.value;
            renderUI();
        });
        document.getElementById("btn-refresh-users").addEventListener("click", () => {
            loadUsers();
        });
        document.getElementById("btn-create-user").addEventListener("click", () => {
            window.openCreateUserModal();
        });

        // Set focus back to search if it was focused (naive preservation)
        if (document.activeElement && document.activeElement.id === 'um-search') {
            const input = document.getElementById("um-search");
            const val = input.value;
            input.focus();
            input.value = '';
            input.value = val;
        }
    };

    const viewUserDetails = async (personId) => {
        if (!personId) return;
        
        let panel = document.getElementById("user-intelligence-panel");
        if (!panel) {
            panel = document.createElement("div");
            panel.id = "user-intelligence-panel";
            panel.className = "glass-panel";
            panel.style.cssText = `
                position: fixed; top: 0; right: 0; width: 450px; height: 100vh;
                background: rgba(10, 15, 25, 0.95); border-left: 1px solid var(--border-color);
                box-shadow: -5px 0 25px rgba(0,0,0,0.8); z-index: 1000;
                transform: translateX(100%); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                overflow-y: auto; padding: 30px; color: var(--text-primary);
            `;
            document.body.appendChild(panel);
        }
        
        // slide in
        setTimeout(() => panel.style.transform = "translateX(0)", 10);
        
        panel.innerHTML = `<div style="text-align:center; padding: 50px; color: var(--accent-color); font-family: var(--font-heading);"><i class="fas fa-circle-notch fa-spin"></i> FETCHING INTELLIGENCE...</div>`;
        
        try {
            const [profRes, actRes] = await Promise.all([
                fetch(`/api/v1/admin/people/${personId}/profile`, { headers: { "Authorization": `Bearer ${sessionId}` } }),
                fetch(`/api/v1/admin/people/${personId}/activity?limit=10`, { headers: { "Authorization": `Bearer ${sessionId}` } })
            ]);
            
            if (!profRes.ok) throw new Error("Profile not found");
            const profile = await profRes.json();
            const activityData = actRes.ok ? await actRes.json() : { items: [] };

            // Fetch snapshot image properly
            let snapshotBase64 = null;
            if (profile.has_latest_snapshot) {
                try {
                    const snapRes = await fetch(`/api/v1/admin/people/${personId}/snapshots?include_image=true`, { headers: { "Authorization": `Bearer ${sessionId}` } });
                    if (snapRes.ok) {
                        const snapData = await snapRes.json();
                        if (snapData.snapshots && snapData.snapshots.length > 0) {
                            snapshotBase64 = snapData.snapshots[0].image_base64;
                        }
                    }
                } catch (e) {
                    // ignore
                }
            }
            
            const fDate = (ts) => ts ? new Date(ts * 1000).toLocaleString() : "Unavailable";
            const fTime = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString() : "";
            
            panel.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; border-bottom: 1px solid var(--border-color); padding-bottom: 15px;">
                    <h2 style="margin:0; font-family: var(--font-heading); color: var(--accent-color);"><i class="fas fa-id-card"></i> User Intelligence</h2>
                    <button class="btn-secondary btn-sm" onclick="document.getElementById('user-intelligence-panel').style.transform = 'translateX(100%)'"><i class="fas fa-times"></i> Close</button>
                </div>
                
                <!-- SECURITY RISK -->
                <div style="margin-bottom: 30px; background: rgba(0,0,0,0.4); padding: 15px; border-radius: 8px; border: 1px solid ${profile.risk_level === 'HIGH' ? 'var(--accent-danger)' : (profile.risk_level === 'MEDIUM' ? 'var(--warning-color)' : 'var(--success-color)')}; box-shadow: 0 0 15px ${profile.risk_level === 'HIGH' ? 'rgba(255, 68, 68, 0.1)' : 'transparent'};">
                    <div style="font-weight: bold; font-size: 1.1em; margin-bottom: 8px; color: ${profile.risk_level === 'HIGH' ? 'var(--accent-danger)' : (profile.risk_level === 'MEDIUM' ? 'var(--warning-color)' : 'var(--success-color)')};">
                        <i class="fas ${profile.risk_level === 'HIGH' ? 'fa-shield-alt' : (profile.risk_level === 'MEDIUM' ? 'fa-exclamation-triangle' : 'fa-shield-check')}"></i> RISK LEVEL: ${profile.risk_level || 'LOW'}
                    </div>
                    <ul style="margin: 0; padding-left: 25px; color: var(--text-primary); font-size: 0.9em; line-height: 1.5;">
                        ${(profile.risk_reasons || ['No data']).map(r => `<li>${r}</li>`).join('')}
                    </ul>
                </div>

                <!-- 1. IDENTITY -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">IDENTITY</h4>
                    <div style="display: flex; gap: 20px; align-items: center;">
                        ${snapshotBase64 
                            ? `<img src="data:image/jpeg;base64,${snapshotBase64}" style="width: 80px; height: 80px; border-radius: 8px; border: 1px solid var(--accent-color); object-fit: cover; box-shadow: 0 0 10px rgba(0,208,255,0.2);" />` 
                            : `<div style="width: 80px; height: 80px; border-radius: 8px; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-color);"><i class="fas fa-user" style="font-size: 30px; color: var(--text-secondary);"></i></div>`
                        }
                        <div>
                            <div style="font-size: 1.2em; font-weight: bold; color: var(--text-primary);">${profile.display_name || 'Unknown'}</div>
                            <div style="color: var(--text-secondary);">@${profile.username || 'Unavailable'}</div>
                            <div style="font-family: monospace; font-size: 0.85em; margin-top: 5px; color: var(--accent-color);">${profile.person_id}</div>
                            <div style="margin-top: 8px; display: flex; gap: 8px;">
                                <span class="status-badge" style="background: rgba(255,255,255,0.1);">${profile.role || 'Unavailable'}</span>
                                <span class="status-badge ${profile.account_enabled ? 'success' : 'danger'}">${profile.account_enabled ? 'ACTIVE' : 'DISABLED'}</span>
                            </div>
                        </div>
                    </div>
                    <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 15px;">Created: ${fDate(profile.created_at)}</div>
                </div>
                
                <!-- 2. BIOMETRIC PROFILE -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">BIOMETRIC PROFILE</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.9em;">
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Status</span> <span class="status-badge ${profile.face_enrollment_status === 'ENROLLED' ? 'success' : 'warning'}" style="margin-top:4px;">${profile.face_enrollment_status || 'Unavailable'}</span></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Templates</span> <div style="margin-top:4px; font-weight:bold;">${profile.template_count || 0}</div></div>
                        <div style="grid-column: span 2;"><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Enrolled</span> <div style="margin-top:4px;">${fDate(profile.enrolled_at)}</div></div>
                        <div style="grid-column: span 2;"><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Last Verification</span> <div style="margin-top:4px;">${fDate(profile.last_biometric_verification)}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Result</span> <div style="margin-top:4px; font-weight:bold; color:${profile.latest_verification_result === 'SUCCESS' ? 'var(--success-color)' : (profile.latest_verification_result ? 'var(--accent-danger)' : 'var(--text-primary)')}">${profile.latest_verification_result || 'None'}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Confidence Score</span> <div style="margin-top:4px;">${profile.latest_verification_score ? profile.latest_verification_score.toFixed(4) : 'N/A'}</div></div>
                    </div>
                </div>
                
                <!-- 3. LIVE ACCESS STATUS -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">LIVE ACCESS STATUS</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.9em;">
                        <div>
                            ${profile.online 
                                ? '<div style="color:var(--success-color); font-weight: bold; margin-top: 4px;"><i class="fas fa-circle" style="text-shadow: 0 0 5px var(--success-color);"></i> Online</div>' 
                                : '<div style="color:var(--text-secondary); margin-top: 4px;"><i class="far fa-circle"></i> Offline</div>'}
                        </div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Session ID</span> <div style="margin-top:4px; font-family: monospace;">${profile.current_session_id ? profile.current_session_id.substring(0,8)+'...' : 'None'}</div></div>
                        <div style="grid-column: span 2;"><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Login Time</span> <div style="margin-top:4px;">${fDate(profile.session_started_at)}</div></div>
                    </div>
                </div>
                
                <!-- 4. LAST ACCESS -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">LAST ACCESS</h4>
                    <div style="display: grid; grid-template-columns: 1fr; gap: 12px; font-size: 0.9em;">
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Timestamp</span> <div style="margin-top:4px;">${fDate(profile.last_access_timestamp || profile.last_login)}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">IP Address</span> <div style="margin-top:4px; font-family: monospace;">${profile.last_access_ip || 'Unavailable'}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Device Info</span> <div style="margin-top:4px;">${profile.last_access_device || 'Unavailable'}</div></div>
                        
                        <div>
                            <span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Location</span>
                            <div style="margin-top: 8px;">
                                ${profile.last_access_location 
                                    ? `
                                    <div style="margin-bottom: 8px;">
                                        <span style="color:var(--accent-color);"><i class="fas fa-map-marker-alt"></i> ${profile.last_access_location.latitude.toFixed(4)}, ${profile.last_access_location.longitude.toFixed(4)}</span>
                                        <span style="color:var(--text-secondary); font-size: 0.9em; margin-left: 10px;">(Accuracy: ${profile.last_access_location.accuracy}m)</span>
                                    </div>
                                    <div style="width: 100%; height: 200px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color);">
                                        <iframe width="100%" height="100%" frameborder="0" scrolling="no" marginheight="0" marginwidth="0" 
                                            src="https://www.openstreetmap.org/export/embed.html?bbox=${profile.last_access_location.longitude - 0.01}%2C${profile.last_access_location.latitude - 0.01}%2C${profile.last_access_location.longitude + 0.01}%2C${profile.last_access_location.latitude + 0.01}&amp;layer=mapnik&amp;marker=${profile.last_access_location.latitude}%2C${profile.last_access_location.longitude}" 
                                            style="border: none; filter: invert(90%) hue-rotate(180deg) contrast(80%); pointer-events: auto;">
                                        </iframe>
                                    </div>
                                    ` 
                                    : (profile.location_permission === 'denied' 
                                        ? '<span style="color:var(--accent-danger);"><i class="fas fa-ban"></i> Location permission denied</span>' 
                                        : '<span style="color:var(--text-secondary);"><i class="fas fa-eye-slash"></i> Location not available</span>')
                                }
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 5. VERIFICATION EVIDENCE -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">VERIFICATION EVIDENCE</h4>
                    ${snapshotBase64 ? `
                        <div style="display: flex; gap: 15px; align-items: flex-start; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <img src="data:image/jpeg;base64,${snapshotBase64}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color);" />
                            <div style="font-size: 0.9em; flex: 1;">
                                <div style="margin-bottom: 8px;"><span style="color:var(--text-secondary); font-size: 0.85em; display:block;">Captured At</span>${fDate(profile.latest_verification_timestamp)}</div>
                                <div><span style="color:var(--text-secondary); font-size: 0.85em; display:block; margin-bottom: 4px;">Status</span><span class="status-badge ${profile.latest_verification_result === 'SUCCESS' ? 'success' : 'danger'}">${profile.latest_verification_result}</span></div>
                            </div>
                        </div>
                    ` : '<div style="color: var(--text-secondary); font-style: italic; font-size: 0.9em;">No verification evidence captured.</div>'}
                </div>
                
                <!-- 6. ACTIVITY TIMELINE -->
                <div style="margin-bottom: 25px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">ACTIVITY TIMELINE</h4>
                    <div style="position: relative; padding-left: 15px; border-left: 2px solid rgba(255,255,255,0.1); margin-left: 5px;">
                        ${activityData.items && activityData.items.length > 0 ? activityData.items.map(ev => `
                            <div style="margin-bottom: 20px; position: relative;">
                                <div style="position: absolute; left: -21px; top: 5px; width: 10px; height: 10px; border-radius: 50%; background: ${ev.access_result === 'SUCCESS' ? 'var(--accent-color)' : 'var(--accent-danger)'}; box-shadow: 0 0 8px ${ev.access_result === 'SUCCESS' ? 'var(--accent-color)' : 'var(--accent-danger)'}; border: 2px solid var(--bg-color);"></div>
                                <div style="font-weight: bold; color: var(--text-primary); font-size: 0.95em;">[${ev.event_type.replace(/_/g, ' ')}]</div>
                                <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 2px;">${fDate(ev.timestamp)}</div>
                                ${ev.gps_latitude ? `<div style="font-size: 0.85em; color: var(--accent-color); margin-top: 4px;"><i class="fas fa-map-marker-alt"></i> Location captured</div>` : ''}
                                ${ev.access_result && ev.access_result !== 'SUCCESS' ? `<div style="font-size: 0.85em; color: var(--accent-danger); margin-top: 4px;">${ev.access_result} ${ev.failure_category ? `(${ev.failure_category})` : ''}</div>` : ''}
                            </div>
                        `).join("") : '<div style="color: var(--text-secondary); font-style: italic; font-size: 0.9em;">No activity yet.</div>'}
                    </div>
                </div>
            `;
            
        } catch (err) {
            panel.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                    <h2 style="margin:0; color: var(--accent-danger);"><i class="fas fa-exclamation-triangle"></i> Error</h2>
                    <button class="btn-secondary btn-sm" onclick="document.getElementById('user-intelligence-panel').style.transform = 'translateX(100%)'">Close</button>
                </div>
                <div style="color: var(--accent-danger); padding: 20px; background: rgba(255,0,0,0.1); border-radius: 8px;">${err.message}</div>
            `;
        }
    };

    window.toggleUserStatus = toggleStatus;
    window.enrollUserFace = enrollFace;
    window.sortUsers = handleSort;
    window.viewUserDetails = viewUserDetails;
    
    window.openCreateUserModal = () => {
        let modal = document.getElementById("create-user-modal");
        if (!modal) {
            modal = document.createElement("div");
            modal.id = "create-user-modal";
            modal.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center;
                z-index: 2000; opacity: 0; transition: opacity 0.3s ease;
            `;
            
            modal.innerHTML = `
                <div class="glass-panel" style="width: 450px; padding: 30px; position: relative; transform: translateY(-20px); transition: transform 0.3s ease;">
                    <button class="btn-secondary btn-sm" style="position: absolute; top: 20px; right: 20px; background: transparent; border: none;" onclick="document.getElementById('create-user-modal').style.display='none'">
                        <i class="fas fa-times" style="font-size: 1.2em;"></i>
                    </button>
                    <h2 style="margin-top: 0; color: var(--accent-color); font-family: var(--font-heading);"><i class="fas fa-user-plus"></i> Create User</h2>
                    <div id="cu-error" style="color: var(--accent-danger); background: rgba(255,0,0,0.1); padding: 10px; border-radius: 4px; margin-bottom: 15px; display: none; font-size: 0.9em;"></div>
                    <div id="cu-success" style="color: var(--success-color); background: rgba(0,255,0,0.1); padding: 10px; border-radius: 4px; margin-bottom: 15px; display: none; font-size: 0.9em;"></div>
                    
                    <form id="cu-form" onsubmit="return false;">
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Display Name *</label>
                            <input type="text" id="cu-display" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Username *</label>
                            <input type="text" id="cu-username" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Password *</label>
                            <input type="password" id="cu-password" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Confirm Password *</label>
                            <input type="password" id="cu-confirm" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <div style="margin-bottom: 25px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Role *</label>
                            <select id="cu-role" class="input-field" style="width: 100%; box-sizing: border-box; cursor: pointer;">
                                <option value="USER">USER</option>
                                <option value="ADMIN">ADMIN</option>
                            </select>
                        </div>
                        <button type="submit" id="cu-submit" class="btn-primary" style="width: 100%; padding: 12px; font-weight: bold;">
                            <i class="fas fa-check"></i> CREATE USER
                        </button>
                    </form>
                </div>
            `;
            document.body.appendChild(modal);
            
            document.getElementById("cu-form").addEventListener("submit", async (e) => {
                e.preventDefault();
                const errDiv = document.getElementById("cu-error");
                const succDiv = document.getElementById("cu-success");
                const btn = document.getElementById("cu-submit");
                
                errDiv.style.display = "none";
                succDiv.style.display = "none";
                
                const dName = document.getElementById("cu-display").value.trim();
                const uName = document.getElementById("cu-username").value.trim();
                const pwd = document.getElementById("cu-password").value;
                const conf = document.getElementById("cu-confirm").value;
                const role = document.getElementById("cu-role").value;
                
                if (!dName || !uName || !pwd || !conf) {
                    errDiv.innerText = "All fields are required.";
                    errDiv.style.display = "block";
                    return;
                }
                if (pwd !== conf) {
                    errDiv.innerText = "Passwords do not match.";
                    errDiv.style.display = "block";
                    return;
                }
                
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Creating...';
                
                try {
                    const res = await fetch("/api/v1/admin/users", {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json",
                            "Authorization": `Bearer ${sessionId}`
                        },
                        body: JSON.stringify({
                            username: uName,
                            password: pwd,
                            display_name: dName,
                            role: role,
                            enabled: true
                        })
                    });
                    
                    const data = await res.json();
                    
                    if (!res.ok) {
                        throw new Error(data.error || "Failed to create user");
                    }
                    
                    succDiv.innerText = "User created successfully!";
                    succDiv.style.display = "block";
                    
                    document.getElementById("cu-form").reset();
                    
                    // Refresh table silently in background
                    loadUsers();
                    
                    setTimeout(() => {
                        modal.style.display = "none";
                    }, 1500);
                    
                } catch (err) {
                    errDiv.innerText = err.message;
                    errDiv.style.display = "block";
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-check"></i> CREATE USER';
                }
            });
        }
        
        // Reset form on open
        document.getElementById("cu-form").reset();
        document.getElementById("cu-error").style.display = "none";
        document.getElementById("cu-success").style.display = "none";
        
        modal.style.display = "flex";
        setTimeout(() => {
            modal.style.opacity = "1";
            modal.querySelector(".glass-panel").style.transform = "translateY(0)";
        }, 10);
    };

    window.toggleUserDropdown = (accountId) => {
        // Close all other dropdowns
        document.querySelectorAll('.action-dropdown').forEach(dropdown => {
            if (dropdown.id !== `dropdown-${accountId}`) {
                dropdown.style.display = 'none';
            }
        });
        
        // Toggle the target dropdown
        const dropdown = document.getElementById(`dropdown-${accountId}`);
        if (dropdown) {
            dropdown.style.display = dropdown.style.display === 'none' ? 'block' : 'none';
        }
    };
    
    // Close dropdowns if clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.dropdown-btn') && !e.target.closest('.action-dropdown')) {
            document.querySelectorAll('.action-dropdown').forEach(dropdown => {
                dropdown.style.display = 'none';
            });
        }
    });

    window.openEditUserModal = (accountId, personId, username, displayName, role, enabled) => {
        let modal = document.getElementById("edit-user-modal");
        if (!modal) {
            modal = document.createElement("div");
            modal.id = "edit-user-modal";
            modal.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center;
                z-index: 2000; opacity: 0; transition: opacity 0.3s ease;
            `;
            
            modal.innerHTML = `
                <div class="glass-panel" style="width: 450px; padding: 30px; position: relative; transform: translateY(-20px); transition: transform 0.3s ease;">
                    <button class="btn-secondary btn-sm" style="position: absolute; top: 20px; right: 20px; background: transparent; border: none;" onclick="document.getElementById('edit-user-modal').style.display='none'">
                        <i class="fas fa-times" style="font-size: 1.2em;"></i>
                    </button>
                    <h2 style="margin-top: 0; color: var(--accent-color); font-family: var(--font-heading);"><i class="fas fa-user-edit"></i> Edit User</h2>
                    <div id="eu-error" style="color: var(--accent-danger); background: rgba(255,0,0,0.1); padding: 10px; border-radius: 4px; margin-bottom: 15px; display: none; font-size: 0.9em;"></div>
                    <div id="eu-success" style="color: var(--success-color); background: rgba(0,255,0,0.1); padding: 10px; border-radius: 4px; margin-bottom: 15px; display: none; font-size: 0.9em;"></div>
                    
                    <form id="eu-form" onsubmit="return false;">
                        <input type="hidden" id="eu-account-id" />
                        
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Person ID (Read Only)</label>
                            <input type="text" id="eu-person-id" class="input-field" style="width: 100%; box-sizing: border-box; background: rgba(0,0,0,0.5); color: var(--text-secondary); cursor: not-allowed; font-family: monospace; border: 1px dashed var(--border-color);" readonly />
                        </div>
                        
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Display Name *</label>
                            <input type="text" id="eu-display" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Username *</label>
                            <input type="text" id="eu-username" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Role *</label>
                            <select id="eu-role" class="input-field" style="width: 100%; box-sizing: border-box; cursor: pointer;">
                                <option value="USER">USER</option>
                                <option value="ADMIN">ADMIN</option>
                            </select>
                        </div>
                        <div style="margin-bottom: 25px;">
                            <label style="display:flex; align-items: center; color: var(--text-secondary); font-size: 0.85em; cursor: pointer;">
                                <input type="checkbox" id="eu-enabled" style="margin-right: 10px;" /> Account Enabled
                            </label>
                        </div>
                        <button type="submit" id="eu-submit" class="btn-primary" style="width: 100%; padding: 12px; font-weight: bold;">
                            <i class="fas fa-save"></i> SAVE CHANGES
                        </button>
                    </form>
                </div>
            `;
            document.body.appendChild(modal);
            
            document.getElementById("eu-form").addEventListener("submit", async (e) => {
                e.preventDefault();
                const errDiv = document.getElementById("eu-error");
                const succDiv = document.getElementById("eu-success");
                const btn = document.getElementById("eu-submit");
                
                errDiv.style.display = "none";
                succDiv.style.display = "none";
                
                const accId = document.getElementById("eu-account-id").value;
                const dName = document.getElementById("eu-display").value.trim();
                const uName = document.getElementById("eu-username").value.trim();
                const role = document.getElementById("eu-role").value;
                const enabled = document.getElementById("eu-enabled").checked;
                
                if (!dName || !uName) {
                    errDiv.innerText = "All fields are required.";
                    errDiv.style.display = "block";
                    return;
                }
                
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-circle-notch fa-spin"></i> Saving...';
                
                try {
                    const res = await fetch(`/api/v1/admin/users/${accId}`, {
                        method: "PUT",
                        headers: {
                            "Content-Type": "application/json",
                            "Authorization": `Bearer ${sessionId}`
                        },
                        body: JSON.stringify({
                            username: uName,
                            display_name: dName,
                            role: role,
                            enabled: enabled
                        })
                    });
                    
                    const data = await res.json();
                    if (!res.ok) throw new Error(data.error || "Failed to update user");
                    
                    succDiv.innerText = "User updated successfully!";
                    succDiv.style.display = "block";
                    
                    loadUsers();
                    
                    setTimeout(() => {
                        modal.style.display = "none";
                    }, 1000);
                } catch (err) {
                    errDiv.innerText = err.message;
                    errDiv.style.display = "block";
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-save"></i> SAVE CHANGES';
                }
            });
        }
        
        document.getElementById("eu-error").style.display = "none";
        document.getElementById("eu-success").style.display = "none";
        document.getElementById("eu-account-id").value = accountId;
        
        const pidField = document.getElementById("eu-person-id");
        if (pidField) pidField.value = personId || "N/A";
        
        document.getElementById("eu-username").value = username;
        document.getElementById("eu-display").value = displayName;
        document.getElementById("eu-role").value = role;
        document.getElementById("eu-enabled").checked = enabled;
        
        modal.style.display = "flex";
        setTimeout(() => {
            modal.style.opacity = "1";
            modal.querySelector(".glass-panel").style.transform = "translateY(0)";
        }, 10);
    };

    window.openChangePasswordModal = (accountId, username, displayName, personId) => {
        let modal = document.getElementById("change-password-modal");
        if (!modal) {
            modal = document.createElement("div");
            modal.id = "change-password-modal";
            modal.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
                background: rgba(0,0,0,0.8); display: flex; justify-content: center; align-items: center;
                z-index: 2000; opacity: 0; transition: opacity 0.3s ease;
            `;
            
            modal.innerHTML = `
                <div class="glass-panel" style="width: 450px; padding: 30px; position: relative; transform: translateY(-20px); transition: transform 0.3s ease;">
                    <button class="btn-secondary btn-sm" style="position: absolute; top: 20px; right: 20px; background: transparent; border: none;" onclick="document.getElementById('change-password-modal').style.display='none'">
                        <i class="fas fa-times" style="font-size: 1.2em;"></i>
                    </button>
                    <h2 style="margin-top: 0; color: var(--accent-color); font-family: var(--font-heading);"><i class="fas fa-key"></i> Change Password</h2>
                    <div id="cp-error" style="color: var(--accent-danger); background: rgba(255,0,0,0.1); padding: 10px; border-radius: 4px; margin-bottom: 15px; display: none; font-size: 0.9em;"></div>
                    <div id="cp-success" style="color: var(--success-color); background: rgba(0,255,0,0.1); padding: 10px; border-radius: 4px; margin-bottom: 15px; display: none; font-size: 0.9em;"></div>
                    
                    <form id="cp-form" onsubmit="return false;">
                        <input type="hidden" id="cp-account-id" />
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">User</label>
                            <input type="text" id="cp-display" class="input-field" style="width: 100%; box-sizing: border-box; background: rgba(0,0,0,0.5); color: var(--text-secondary); cursor: not-allowed; border: 1px dashed var(--border-color);" readonly />
                        </div>
                        <div style="margin-bottom: 15px; display: none;" id="cp-current-password-container">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Current Password *</label>
                            <input type="password" id="cp-current-password" class="input-field" style="width: 100%; box-sizing: border-box;" />
                        </div>
                        <div style="margin-bottom: 15px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">New Password *</label>
                            <input type="password" id="cp-new-password" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <div style="margin-bottom: 25px;">
                            <label style="display:block; margin-bottom:5px; color: var(--text-secondary); font-size: 0.85em;">Confirm New Password *</label>
                            <input type="password" id="cp-confirm-password" class="input-field" style="width: 100%; box-sizing: border-box;" required />
                        </div>
                        <button type="submit" id="cp-submit" class="btn-primary" style="width: 100%; padding: 12px; font-weight: bold;">
                            <i class="fas fa-lock"></i> UPDATE PASSWORD
                        </button>
                    </form>
                </div>
            `;
            document.body.appendChild(modal);
            
            document.getElementById("cp-form").addEventListener("submit", async (e) => {
                e.preventDefault();
                const errDiv = document.getElementById("cp-error");
                const succDiv = document.getElementById("cp-success");
                const btn = document.getElementById("cp-submit");
                
                errDiv.style.display = "none";
                succDiv.style.display = "none";
                
                const accId = document.getElementById("cp-account-id").value;
                const currPass = document.getElementById("cp-current-password").value;
                const newPass = document.getElementById("cp-new-password").value;
                const confPass = document.getElementById("cp-confirm-password").value;
                
                if (newPass !== confPass) {
                    errDiv.innerText = "New passwords do not match.";
                    errDiv.style.display = "block";
                    return;
                }
                
                if (newPass.length < 8) {
                    errDiv.innerText = "Password must be at least 8 characters.";
                    errDiv.style.display = "block";
                    return;
                }
                
                const payload = { new_password: newPass };
                const currentAccountId = localStorage.getItem("atlas_session_account_id");
                if (currentAccountId === accId) {
                    if (!currPass) {
                        errDiv.innerText = "Current password is required to change your own password.";
                        errDiv.style.display = "block";
                        return;
                    }
                    payload.current_password = currPass;
                }
                
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> UPDATING...';
                
                try {
                    const res = await fetch(`/api/v1/admin/users/${accId}/password`, {
                        method: "PUT",
                        headers: {
                            "Content-Type": "application/json",
                            "Authorization": `Bearer ${sessionId}`
                        },
                        body: JSON.stringify(payload)
                    });
                    
                    if (!res.ok) {
                        const d = await res.json();
                        throw new Error(d.error || "Failed to update password");
                    }
                    
                    succDiv.innerText = "Password updated successfully.";
                    succDiv.style.display = "block";
                    
                    // Clear inputs securely
                    document.getElementById("cp-current-password").value = "";
                    document.getElementById("cp-new-password").value = "";
                    document.getElementById("cp-confirm-password").value = "";
                    
                    setTimeout(() => {
                        modal.style.display = "none";
                        // If it was the current user, session is revoked, page should auto-refresh or logout
                        if (currentAccountId === accId) {
                            window.location.reload();
                        } else {
                            loadUsers();
                        }
                    }, 1500);
                } catch (err) {
                    errDiv.innerText = err.message;
                    errDiv.style.display = "block";
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="fas fa-lock"></i> UPDATE PASSWORD';
                }
            });
        }
        
        // Setup Modal State
        setTimeout(() => {
            modal.style.opacity = "1";
            modal.querySelector(".glass-panel").style.transform = "translateY(0)";
        }, 10);
        
        document.getElementById("cp-error").style.display = "none";
        document.getElementById("cp-success").style.display = "none";
        document.getElementById("cp-account-id").value = accountId;
        
        document.getElementById("cp-display").value = `${displayName} (@${username})`;
        
        const currentAccountId = localStorage.getItem("atlas_session_account_id");
        if (currentAccountId === accountId) {
            document.getElementById("cp-current-password-container").style.display = "block";
            document.getElementById("cp-current-password").required = true;
        } else {
            document.getElementById("cp-current-password-container").style.display = "none";
            document.getElementById("cp-current-password").required = false;
        }
        
        document.getElementById("cp-current-password").value = "";
        document.getElementById("cp-new-password").value = "";
        document.getElementById("cp-confirm-password").value = "";
        
        modal.style.display = "flex";
    };

    window.confirmDeleteUser = (accountId, username) => {
        if (confirm(`Are you SURE you want to permanently delete ${username}?\nThis action cannot be undone.`)) {
            fetch(`/api/v1/admin/users/${accountId}`, {
                method: "DELETE",
                headers: { "Authorization": `Bearer ${sessionId}` }
            }).then(async res => {
                const data = await res.json();
                if (!res.ok) alert("Error deleting user: " + (data.error || "Unknown"));
                else loadUsers();
            }).catch(e => alert("Network error"));
        }
    };

    window.confirmResetBiometrics = (personId, username) => {
        if (confirm(`Are you sure you want to reset biometrics for ${username}?`)) {
            fetch(`/api/v1/admin/people/${personId}/reset-biometrics`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${sessionId}` }
            }).then(async res => {
                const data = await res.json();
                if (!res.ok) alert("Error resetting biometrics: " + (data.error || "Unknown"));
                else loadUsers();
            }).catch(e => alert("Network error"));
        }
    };



    loadUsers();
}


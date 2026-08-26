(function(){let e=document.createElement(`link`).relList;if(e&&e.supports&&e.supports(`modulepreload`))return;for(let e of document.querySelectorAll(`link[rel="modulepreload"]`))n(e);new MutationObserver(e=>{for(let t of e)if(t.type===`childList`)for(let e of t.addedNodes)e.tagName===`LINK`&&e.rel===`modulepreload`&&n(e)}).observe(document,{childList:!0,subtree:!0});function t(e){let t={};return e.integrity&&(t.integrity=e.integrity),e.referrerPolicy&&(t.referrerPolicy=e.referrerPolicy),t.credentials=e.crossOrigin===`use-credentials`?`include`:e.crossOrigin===`anonymous`?`omit`:`same-origin`,t}function n(e){if(e.ep)return;e.ep=!0;let n=t(e);fetch(e.href,n)}})();var e=class e{static async _safeParseJson(e){let t=await e.text(),n={};if(t)try{n=JSON.parse(t)}catch{throw console.error(`[BIOMETRIC] Backend returned non-JSON response:`,t),Error(`Server returned an invalid response (HTTP ${e.status})`)}return n}static async getStatus(t){let n=await fetch(`/api/v1/biometric/status/${t}`),r=await e._safeParseJson(n);if(!n.ok)throw Error(r.message||`Failed to fetch biometric status`);return r}static async enroll(t,n=null){let r={person_id:t};n&&(r.image_data=n);let i=await fetch(`/api/v1/biometric/enroll`,{method:`POST`,headers:{"Content-Type":`application/json`},body:JSON.stringify(r)}),a=await e._safeParseJson(i);if(!i.ok)throw Error(a.message||a.reason||`Enrollment failed`);return a}static async verify(t,n=null,r=null){let i={person_id:t};n&&(i.image_data=n),r&&(i.gps_location={latitude:r.latitude,longitude:r.longitude,accuracy:r.accuracy,timestamp:r.timestamp,status:r.status});let a=await fetch(`/api/v1/biometric/verify`,{method:`POST`,headers:{"Content-Type":`application/json`},body:JSON.stringify(i)}),o=await e._safeParseJson(a);if(!a.ok&&a.status===500)throw Error(o.message||`Verification failed due to server error`);return o}static async reset(t,n){let r=await fetch(`/api/v1/biometric/reset`,{method:`POST`,headers:{"Content-Type":`application/json`},body:JSON.stringify({username:t,password:n})}),i=await e._safeParseJson(r);if(!r.ok)throw Error(i.message||`Failed to reset biometric profile`);return i}},t=5e3;function n(){return new Promise(e=>{if(!navigator.geolocation){e({latitude:null,longitude:null,accuracy:null,timestamp:null,status:`unsupported`});return}let n=setTimeout(()=>{e({latitude:null,longitude:null,accuracy:null,timestamp:null,status:`unavailable`})},5500);navigator.geolocation.getCurrentPosition(t=>{clearTimeout(n),e({latitude:t.coords.latitude,longitude:t.coords.longitude,accuracy:t.coords.accuracy,timestamp:t.timestamp/1e3,status:`granted`})},t=>{clearTimeout(n),e({latitude:null,longitude:null,accuracy:null,timestamp:null,status:t.code===1?`denied`:`unavailable`})},{enableHighAccuracy:!1,timeout:t,maximumAge:3e4})})}function r(e){if(!e)return`<span class="loc-badge loc-unavailable">&#9679; Location Unavailable</span>`;switch(e.status){case`granted`:return`<span class="loc-badge loc-granted">&#9679; Location Captured${e.accuracy==null?``:` &mdash; &plusmn;${Math.round(e.accuracy)}m`}</span>`;case`denied`:return`<span class="loc-badge loc-denied">&#9679; Permission Denied</span>`;default:return`<span class="loc-badge loc-unavailable">&#9679; Location Unavailable</span>`}}function i(t,i,a,o,s,c,l){let u=document.getElementById(t);if(!u)return;u.innerHTML=`
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
    `;let d=document.getElementById(`btn-verify-face`),f=document.getElementById(`btn-cancel-verify`),p=document.getElementById(`biometric-error-message`),m=document.getElementById(`biometric-state-display`),h=document.getElementById(`biometric-video`),g=document.getElementById(`biometric-canvas`),_=document.getElementById(`video-container`),v=document.getElementById(`link-reset-biometrics`),y=document.getElementById(`biometric-loc-badge`),b=null,x=!1,S=s||null;y&&(y.innerHTML=r(S));let C=()=>{x=!1,b&&=(b.getTracks().forEach(e=>e.stop()),null)};f.addEventListener(`click`,()=>{C(),l&&l()}),v&&v.addEventListener(`click`,async t=>{if(t.preventDefault(),confirm(`Are you sure you want to reset your biometric profile? This will delete your current face templates and allow credentials-only access.`)){C(),m.innerHTML=`
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--warning-color); box-shadow: 0 0 8px var(--warning-color);"></span>
                    Resetting biometric profile...
                </div>
            `;try{await e.reset(a,o),m.innerHTML=`
                    <div class="status-indicator">
                        <span class="status-dot" style="background: var(--success-color); box-shadow: 0 0 8px var(--success-color);"></span>
                        Reset Successful!
                    </div>
                `,setTimeout(()=>c(null),1500)}catch(e){console.error(e),p.innerText=e.message||`Failed to reset biometric profile.`,p.style.display=`block`,m.innerHTML=`
                    <div class="status-indicator">
                        <span class="status-dot" style="background: var(--error-color);"></span>
                        Reset Failed
                    </div>
                `}}});let w=async()=>{if(!x)return;let t=g.getContext(`2d`);if(h.videoWidth>0&&h.videoHeight>0){g.width=h.videoHeight,g.height=h.videoWidth,t.clearRect(0,0,g.width,g.height),t.save(),t.translate(g.width/2,g.height/2),t.rotate(90*Math.PI/180),t.drawImage(h,-h.videoWidth/2,-h.videoHeight/2,h.videoWidth,h.videoHeight),t.restore();let n=g.toDataURL(`image/jpeg`,.8);try{let t=await e.verify(i,n,S);if(t.success&&t.verified){C(),m.innerHTML=`
                        <div class="status-indicator">
                            <span class="status-dot" style="background: var(--success-color); box-shadow: 0 0 8px var(--success-color);"></span>
                            Identity Verified
                        </div>
                    `,setTimeout(()=>c(t.verification_token),1e3);return}{let e=`Verification failed.`;if(t.reason===`NO_FACE`)e=`No face was detected.`;else if(t.reason===`MULTIPLE_FACES`)e=`Multiple faces detected.`;else if(t.reason===`QUALITY_REJECTED`)e=`Face quality insufficient.`;else if(t.reason===`RE_ENROLLMENT_REQUIRED`){C(),p.innerText=`Biometric profile is outdated. Please re-enroll.`,p.style.display=`block`,d.disabled=!1,f.disabled=!1;return}else if(t.reason===`NOT_ENROLLED`){C(),p.innerText=`No biometric profile found.`,p.style.display=`block`,d.disabled=!1,f.disabled=!1;return}m.innerHTML=`
                        <div class="status-indicator">
                            <span class="status-dot" style="background: var(--warning-color); box-shadow: 0 0 8px var(--warning-color);"></span>
                            ${e} Retrying...
                        </div>
                    `}}catch(e){console.error(e)}}x&&setTimeout(w,1e3)};d.addEventListener(`click`,async()=>{d.disabled=!0,p.style.display=`none`,S||(console.log(`[LOCATION] No prior GPS data — requesting at biometric gate...`),S=await n(),console.log(`[LOCATION] Biometric gate GPS result:`,S),y&&(y.innerHTML=r(S)));try{b=await navigator.mediaDevices.getUserMedia({video:!0}),h.srcObject=b,_.style.display=`block`,x=!0,m.innerHTML=`
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--primary-color); box-shadow: 0 0 8px var(--primary-color);"></span>
                    Please look at the camera...
                </div>
            `,setTimeout(w,1e3)}catch(e){console.error(e),d.disabled=!1,p.innerText=`Camera access denied or unavailable.`,p.style.display=`block`,m.innerHTML=`
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--error-color);"></span>
                    Camera Error
                </div>
            `}})}function a(e){console.log(`[ATLAS FRONTEND] renderLoginPage started`),document.getElementById(`app`).innerHTML=`
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
    `;let t=document.getElementById(`login-form`),o=document.getElementById(`btn-submit`),s=document.getElementById(`error-message`),c=document.getElementById(`loc-badge-container`),l=async(e,t,n=null,r=null)=>{let i={username:e,password:t};n&&(i.biometric_input=n),r&&(i.gps_location={latitude:r.latitude,longitude:r.longitude,accuracy:r.accuracy,timestamp:r.timestamp,status:r.status});let a=await fetch(`/api/v1/auth/login`,{method:`POST`,headers:{"Content-Type":`application/json`},body:JSON.stringify(i)}),o=await a.text(),s={};if(o)try{s=JSON.parse(o)}catch{throw console.error(`[LOGIN] Backend returned non-JSON response:`,o),Error(`Server returned an invalid response (HTTP ${a.status})`)}return{ok:a.ok,data:s}};t.addEventListener(`submit`,async t=>{t.preventDefault();let u=document.getElementById(`username`).value,d=document.getElementById(`password`).value;s.style.display=`none`,o.disabled=!0,console.log(`[LOCATION] Requesting browser GPS...`);let f=await n();console.log(`[LOCATION] Result:`,f),c&&(c.innerHTML=r(f));try{let{ok:t,data:n}=await l(u,d,null,f);if(t&&n.authenticated)e(n.role,n.session_id);else if(!n.authenticated&&n.biometric_required){let t=document.getElementById(`login-card-content`),r=t.innerHTML;t.innerHTML=`<div id="biometric-gate-container"></div>`,i(`biometric-gate-container`,n.person_id,u,d,f,async n=>{try{let t=await l(u,d,n,f);if(t.ok&&t.data.authenticated)e(t.data.role,t.data.session_id);else throw Error(`Final authentication failed after biometrics.`)}catch(e){t.innerHTML=r,document.getElementById(`error-message`).innerText=e.message||`AUTHENTICATION FAILED`,document.getElementById(`error-message`).style.display=`block`,document.getElementById(`btn-submit`).disabled=!1}},()=>{t.innerHTML=r,document.getElementById(`btn-submit`).disabled=!1,a(e)})}else throw Error(n.message||`AUTHENTICATION FAILED`)}catch(e){s.innerText=e.message||`AUTHENTICATION FAILED`,s.style.display=`block`,o.disabled=!1}})}function o(e,t=`overview`){let n=e.toUpperCase()===`ADMIN`;return`
        <div class="sidebar">
            <div class="sidebar-header-wrapper">
                <div class="sidebar-header">
                    <h2 class="sidebar-title">ATLAS OS</h2>
                    <span class="sidebar-subtitle">Autonomous System</span>
                </div>
                <ul class="sidebar-menu">
                    <li class="menu-item">
                        <a class="menu-link ${t===`overview`?`active`:``}" id="nav-overview">
                            System Overview
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${t===`devices`?`active`:``}" id="nav-devices">
                            Devices
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${t===`events`?`active`:``}" id="nav-events">
                            Events & Alerts
                        </a>
                    </li>
                    ${n?`
                    <li class="menu-item">
                        <a class="menu-link ${t===`users`?`active`:``}" id="nav-users">
                            User Management
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${t===`security`?`active`:``}" id="nav-security">
                            Security Logs
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${t===`config`?`active`:``}" id="nav-config">
                            System Configuration
                        </a>
                    </li>
                    `:``}
                </ul>
            </div>
            <div class="sidebar-footer">
                <div class="user-badge">${e} Session Active</div>
                <button class="btn-primary" id="btn-logout" style="padding: 10px; font-size: 0.8rem;">
                    Disconnect
                </button>
            </div>
        </div>
    `}function s(e){return!e||e.length===0?`
            <div class="panel-card glass-panel">
                <div class="card-title">Registered Devices</div>
                <div style="color: var(--text-secondary); font-size: 0.9rem; text-align: center; padding: 30px 0;">
                    No devices discovered in registry.
                </div>
            </div>
        `:`
        <div class="panel-card glass-panel">
            <div class="card-title">Registered Devices</div>
            <div style="max-height: 300px; overflow-y: auto;">
                ${e.map(e=>`
        <div class="device-item">
            <div>
                <strong style="display: block; font-family: var(--font-heading); font-size: 0.95rem;">${e.device_id}</strong>
                <span style="font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase;">
                    Type: ${e.device_type}
                </span>
            </div>
            <div>
                <span class="badge-online">${e.status}</span>
            </div>
        </div>
    `).join(``)}
            </div>
        </div>
    `}function c(e,t){let n=(t||[]).map(e=>`
        <div class="alert-item">
            <div class="event-meta">
                <span style="color: var(--accent-danger); font-weight: bold;">[${e.severity}]</span>
                <span>${e.timestamp}</span>
            </div>
            <div class="event-details">${e.message}</div>
        </div>
    `).join(``),r=(e||[]).map(e=>`
        <div class="event-item">
            <div class="event-meta">
                <span style="color: var(--accent-color);">[EVENT]</span>
                <span>${e.timestamp}</span>
            </div>
            <div class="event-details">
                <strong>${e.event_type}</strong> triggered by <em>${e.source}</em>
            </div>
        </div>
    `).join(``);return`
        <div class="panel-card glass-panel">
            <div class="card-title">Live Diagnostics Log</div>
            <div style="max-height: 320px; overflow-y: auto;">
                ${n}
                ${r}
                ${n.length===0&&r.length===0?`
                    <div style="color: var(--text-muted); font-size: 0.85rem; text-align: center; padding: 30px 0;">
                        Diagnostics clear. No active events.
                    </div>
                `:``}
            </div>
        </div>
    `}function l(e,t){return`
        <div class="panel-card glass-panel">
            <div class="card-title">System Status Overview</div>
            <div class="status-item">
                <span>Core Operating Status</span>
                <span style="color: #39ff14; font-weight: bold;">${e}</span>
            </div>
            <div class="status-item">
                <span>ATLAS Reasoning Mode</span>
                <span style="color: var(--accent-color); font-weight: bold;">AUTONOMOUS</span>
            </div>
            <div class="status-item">
                <span>Active Network Gateway</span>
                <span style="color: #39ff14; font-weight: bold;">ONLINE</span>
            </div>
            <div class="status-item">
                <span>Biometric Profile Match</span>
                <span style="color: var(--accent-color); font-weight: bold;">CONFIRMED</span>
            </div>
            <div class="status-item">
                <span>Session Clearance</span>
                <span style="color: var(--accent-color); font-weight: bold; text-transform: uppercase;">${t}</span>
            </div>
        </div>
    `}function u(t,n){let r=document.getElementById(t);if(!r)return;let i=`IDLE`,a=null,o=null,s=!1,c=()=>{s=!1,o&&=(o.getTracks().forEach(e=>e.stop()),null)},l=()=>{let e=``;i===`CHECKING_STATUS`||i===`IDLE`?e=`
                <div class="status-indicator">
                    <span class="status-dot" style="background: var(--warning-color); box-shadow: 0 0 8px var(--warning-color);"></span>
                    Checking biometric profile...
                </div>
            `:i===`NOT_ENROLLED`?e=`
                <p style="margin-bottom: 15px;">No biometric profile found. Face authentication has not been configured.</p>
                <button class="btn-primary" id="btn-enroll-action">Enroll Face Now</button>
            `:i===`ENROLLED`?e=`
                <p style="margin-bottom: 15px; color: var(--success-color);">Face authentication successfully configured.</p>
                <p style="margin-bottom: 15px; font-size: 0.9em; color: var(--text-secondary);">
                    Templates: ${a?.template_count||5} | Dimension: ${a?.embedding_dimension||512}
                </p>
                <button class="btn-secondary" id="btn-enroll-action">Re-enroll Face</button>
            `:i===`ENROLLING`?e=`
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
            `:i===`ERROR`&&(e=`
                <div class="error-text" style="display: block; margin-bottom: 15px;" id="enroll-error-msg"></div>
                <button class="btn-primary" id="btn-enroll-action">Try Again</button>
            `),r.innerHTML=`
            <div class="glass-panel" style="margin-bottom: 20px;">
                <h3 style="margin-bottom: 15px; font-weight: 600;">Biometric Authentication</h3>
                ${e}
            </div>
        `;let t=document.getElementById(`btn-enroll-action`);t&&t.addEventListener(`click`,d);let n=document.getElementById(`btn-cancel-enroll`);n&&n.addEventListener(`click`,()=>{c(),u()})},u=async()=>{i=`CHECKING_STATUS`,l();try{let t=await e.getStatus(n);a=t,i=t.enrolled?`ENROLLED`:`NOT_ENROLLED`,l()}catch{i=`ERROR`,l(),document.getElementById(`enroll-error-msg`).innerText=`Failed to load biometric status.`}},d=async()=>{i=`ENROLLING`,l();let t=document.getElementById(`biometric-enroll-video`),r=document.getElementById(`biometric-enroll-canvas`),a=document.getElementById(`enroll-progress-display`),d=document.getElementById(`enroll-error-msg`);try{o=await navigator.mediaDevices.getUserMedia({video:!0,audio:!1}),t.srcObject=o,s=!0,t.onloadedmetadata=()=>{t.play(),f()}}catch{i=`ERROR`,l(),document.getElementById(`enroll-error-msg`).innerText=`Camera access denied or unavailable.`}let f=async()=>{if(!s)return;let o=r.getContext(`2d`);if(t.videoWidth>0&&t.videoHeight>0){r.width=t.videoHeight,r.height=t.videoWidth,o.clearRect(0,0,r.width,r.height),o.save(),o.translate(r.width/2,r.height/2),o.rotate(90*Math.PI/180),o.drawImage(t,-t.videoWidth/2,-t.videoHeight/2,t.videoWidth,t.videoHeight),o.restore();let s=r.toDataURL(`image/jpeg`,.8);try{let t=await e.enroll(n,s);if(t.success){c(),a.innerText=`Enrollment complete`,a.style.color=`#39ff14`,setTimeout(()=>u(),1500);return}if(t.error===`Collecting`)a.innerText=`Sample ${t.samples_captured} / ${t.samples_requested}`,t.reason?(d.innerText=t.reason,d.style.display=`block`):d.style.display=`none`;else{c(),i=`ERROR`,l();let e=t.message||t.reason||`Enrollment failed.`;t.reason===`CAMERA_BUSY`&&(e=`Another biometric operation is currently using the camera.`),document.getElementById(`enroll-error-msg`).innerText=e;return}}catch{}}s&&setTimeout(f,1e3)}};u()}function d(e,t,n){let r=document.getElementById(`app`);r.innerHTML=`
        <div class="dashboard-wrapper">
            ${o(e,`overview`)}
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
    `,document.getElementById(`btn-logout`).addEventListener(`click`,()=>{n()});async function i(){try{let e=await fetch(`/api/v1/dashboard`,{method:`GET`,headers:{Authorization:`Bearer ${t}`}});if(!e.ok)throw Error(`Failed to load dashboard statistics.`);let n=await e.json(),r=document.getElementById(`dashboard-content`);r.innerHTML=`
                <div class="grid-col">
                    ${l(n.system_status,n.role)}
                    <div style="margin-top: 25px;"></div>
                    <div id="biometric-enrollment-container"></div>
                    <div style="margin-top: 25px;"></div>
                    ${s(n.devices)}
                </div>
                <div class="grid-col">
                    ${c(n.recent_events,n.alerts)}
                </div>
            `,n.person_id&&u(`biometric-enrollment-container`,n.person_id)}catch(e){document.getElementById(`dashboard-content`).innerHTML=`
                <div style="grid-column: span 2; text-align: center; color: var(--accent-danger); padding: 50px 0;">
                    ${e.message||`Failed to load telemetry.`}
                </div>
            `}}i()}function f(t,n,r){let i=document.getElementById(t);if(!i)return;let a=[],o={searchQuery:``,roleFilter:`ALL`,statusFilter:`ALL`,bioFilter:`ALL`,onlineFilter:`ALL`,sortColumn:`username`,sortDirection:`asc`},s=async()=>{try{i.innerHTML=`<div style="text-align:center; padding:50px; color:var(--accent-color);">LOADING USER DATA...</div>`;let e=await fetch(`/api/v1/admin/users`,{headers:{Authorization:`Bearer ${n}`}});if(!e.ok)throw Error(`Failed to load users`);a=(await e.json()).users||[],p()}catch(e){i.innerHTML=`<div class="error-text">Failed to load user management: ${e.message}</div>`}},c=async(e,t)=>{try{(await fetch(`/api/v1/admin/users/${e}/status`,{method:`POST`,headers:{"Content-Type":`application/json`,Authorization:`Bearer ${n}`},body:JSON.stringify({enabled:t})})).ok?await s():alert(`Failed to update status`)}catch(e){alert(e.message)}},l=t=>{let n=document.createElement(`div`);n.className=`biometric-modal-overlay`,n.innerHTML=`
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
        `,document.body.appendChild(n);let r=document.getElementById(`modal-enroll-video`),i=document.getElementById(`modal-enroll-canvas`),a=document.getElementById(`modal-enroll-progress`),o=document.getElementById(`modal-enroll-error`),c=document.getElementById(`btn-modal-cancel`),l=null,u=!0,d=()=>{u=!1,l&&=(l.getTracks().forEach(e=>e.stop()),null)};c.addEventListener(`click`,()=>{d(),n.remove()});let f=async()=>{try{l=await navigator.mediaDevices.getUserMedia({video:!0,audio:!1}),r.srcObject=l,r.onloadedmetadata=()=>{r.play(),p()}}catch{o.innerText=`Camera access denied.`,o.style.display=`block`}},p=async()=>{if(!u)return;let c=i.getContext(`2d`);if(r.videoWidth>0&&r.videoHeight>0){i.width=r.videoHeight,i.height=r.videoWidth,c.clearRect(0,0,i.width,i.height),c.save(),c.translate(i.width/2,i.height/2),c.rotate(90*Math.PI/180),c.drawImage(r,-r.videoWidth/2,-r.videoHeight/2,r.videoWidth,r.videoHeight),c.restore();let l=i.toDataURL(`image/jpeg`,.8);try{let r=await e.enroll(t,l);if(r.success){d(),a.innerText=`Enrollment Complete!`,a.style.color=`#39ff14`,setTimeout(()=>{n.remove(),s()},1500);return}if(r.error===`Collecting`)a.innerText=`Sample ${r.samples_captured} / ${r.samples_requested}`,r.reason?(o.innerText=r.reason,o.style.display=`block`):o.style.display=`none`;else{d(),o.innerText=r.message||r.reason||`Enrollment failed.`,o.style.display=`block`;return}}catch{}}u&&setTimeout(p,1e3)};f()},u=e=>{o.sortColumn===e?o.sortDirection=o.sortDirection===`asc`?`desc`:`asc`:(o.sortColumn=e,o.sortDirection=`asc`),p()},d=()=>{let e=a.filter(e=>{let t=o.searchQuery.toLowerCase(),n=t===``||e.username&&e.username.toLowerCase().includes(t)||e.display_name&&e.display_name.toLowerCase().includes(t)||e.atlas_person_id&&e.atlas_person_id.toLowerCase().includes(t),r=o.roleFilter===`ALL`||e.role===o.roleFilter,i=o.statusFilter===`ALL`||o.statusFilter===`ACTIVE`&&e.enabled||o.statusFilter===`DISABLED`&&!e.enabled,a=o.bioFilter===`ALL`||e.face_enrollment_status===o.bioFilter,s=o.onlineFilter===`ALL`||o.onlineFilter===`ONLINE`&&e.online||o.onlineFilter===`OFFLINE`&&!e.online;return n&&r&&i&&a&&s});return e.sort((e,t)=>{let n=e[o.sortColumn]||``,r=t[o.sortColumn]||``;return o.sortColumn===`name`?(n=e.display_name||``,r=t.display_name||``):o.sortColumn===`last_access`&&(n=e.last_access_timestamp||0,r=t.last_access_timestamp||0),typeof n==`string`&&(n=n.toLowerCase()),typeof r==`string`&&(r=r.toLowerCase()),n<r?o.sortDirection===`asc`?-1:1:n>r?o.sortDirection===`asc`?1:-1:0}),e},f=e=>e?new Date(e*1e3).toLocaleString():`Never`,p=()=>{let e=d(),t=e.map(e=>{let t=`Unknown`;e.gps_latitude&&e.gps_longitude&&(t=`<a href="https://maps.google.com/?q=${e.gps_latitude},${e.gps_longitude}" target="_blank" style="color: var(--accent-color); text-decoration: none;"><i class="fas fa-map-marker-alt"></i> ${e.gps_latitude.toFixed(4)}, ${e.gps_longitude.toFixed(4)}</a>`);let n=e.risk_level||`LOW`,r=`success`;n===`HIGH`?r=`danger`:n===`MEDIUM`&&(r=`warning`);let i=(e.risk_reasons||[`No data`]).join(`&#10;`);return`
                <tr style="border-bottom: 1px solid rgba(255, 255, 255, 0.05); transition: background 0.2s;">
                    <td style="padding: 15px 10px;">
                        <div style="display: flex; align-items: center; gap: 15px;">
                            <div style="width: 40px; height: 40px; border-radius: 50%; background: var(--bg-color); display: flex; align-items: center; justify-content: center; font-size: 18px; color: var(--text-secondary); border: 1px solid var(--border-color);"><i class="fas fa-user"></i></div>
                            <div>
                                <div style="font-weight: bold; color: var(--text-primary);">${e.display_name||`Unknown`}</div>
                                <div style="font-size: 0.85em; color: var(--text-secondary);">@${e.username}</div>
                            </div>
                        </div>
                    </td>
                    <td style="padding: 15px 10px; font-family: monospace; font-size: 0.9em; color: var(--text-secondary);">${e.atlas_person_id||`N/A`}</td>
                    <td style="padding: 15px 10px;"><span class="status-badge" style="background: rgba(255,255,255,0.1);">${e.role}</span></td>
                    <td style="padding: 15px 10px;">
                        <span class="status-badge ${e.enabled?`success`:`danger`}">${e.enabled?`ACTIVE`:`DISABLED`}</span>
                    </td>
                    <td style="padding: 15px 10px;">
                        <span class="status-badge ${e.face_enrollment_status===`ENROLLED`?`success`:e.face_enrollment_status===`FAILED`?`danger`:`warning`}">${e.face_enrollment_status}</span>
                    </td>
                    <td style="padding: 15px 10px;">
                        ${e.online?`<span style="color:var(--success-color); font-weight: bold;"><i class="fas fa-circle" style="font-size: 0.7em; margin-right: 5px; text-shadow: 0 0 5px var(--success-color);"></i>Online</span>`:`<span style="color:var(--text-secondary);"><i class="far fa-circle" style="font-size: 0.7em; margin-right: 5px;"></i>Offline</span>`}
                    </td>
                    <td style="padding: 15px 10px; font-size: 0.9em; color: var(--text-secondary);">
                        ${f(e.last_access_timestamp||e.last_login)}
                    </td>
                    <td style="padding: 15px 10px; font-size: 0.9em;">${t}</td>
                    <td style="padding: 15px 10px;">
                        <span class="status-badge ${r}" title="${i}">${n}</span>
                    </td>
                    <td style="padding: 15px 10px;">
                        <div style="display: flex; gap: 8px;">
                            <button class="btn-secondary btn-sm" onclick="window.viewUserDetails('${e.atlas_person_id}')" title="View Details">
                                <i class="fas fa-eye"></i>
                            </button>
                            <button class="btn-secondary btn-sm" onclick="window.toggleUserStatus('${e.account_id}', ${!e.enabled})" title="${e.enabled?`Disable Account`:`Enable Account`}">
                                <i class="fas ${e.enabled?`fa-user-slash`:`fa-user-check`}"></i>
                            </button>
                            ${e.atlas_person_id?`
                            <button class="btn-primary btn-sm" onclick="window.enrollUserFace('${e.atlas_person_id}')" title="Enroll Face">
                                <i class="fas fa-camera"></i> Enroll
                            </button>
                            `:``}
                        </div>
                    </td>
                </tr>
            `}).join(``),n=e=>o.sortColumn===e?o.sortDirection===`asc`?`<i class="fas fa-sort-up"></i>`:`<i class="fas fa-sort-down"></i>`:`<i class="fas fa-sort" style="opacity: 0.3;"></i>`;if(i.innerHTML=`
            <div class="glass-panel" style="padding: 25px; margin-bottom: 30px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                    <h2 class="card-title" style="margin: 0; display: flex; align-items: center; gap: 10px;">
                        <i class="fas fa-users" style="color: var(--accent-color);"></i> User Management
                    </h2>
                    <button class="btn-secondary btn-sm" id="btn-refresh-users">
                        <i class="fas fa-sync-alt"></i> Refresh
                    </button>
                </div>

                <!-- Controls Bar -->
                <div style="display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 25px; padding: 15px; background: rgba(0, 0, 0, 0.2); border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                    <div style="flex: 1; min-width: 250px;">
                        <input type="text" id="um-search" placeholder="Search by name, username, or ID..." value="${o.searchQuery}" class="input-field" style="width: 100%; padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px;" />
                    </div>
                    <select id="um-filter-role" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${o.roleFilter===`ALL`?`selected`:``}>All Roles</option>
                        <option value="ADMIN" ${o.roleFilter===`ADMIN`?`selected`:``}>Admin</option>
                        <option value="USER" ${o.roleFilter===`USER`?`selected`:``}>User</option>
                    </select>
                    <select id="um-filter-status" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${o.statusFilter===`ALL`?`selected`:``}>All Status</option>
                        <option value="ACTIVE" ${o.statusFilter===`ACTIVE`?`selected`:``}>Active</option>
                        <option value="DISABLED" ${o.statusFilter===`DISABLED`?`selected`:``}>Disabled</option>
                    </select>
                    <select id="um-filter-bio" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${o.bioFilter===`ALL`?`selected`:``}>All Biometrics</option>
                        <option value="ENROLLED" ${o.bioFilter===`ENROLLED`?`selected`:``}>Enrolled</option>
                        <option value="NOT_ENROLLED" ${o.bioFilter===`NOT_ENROLLED`?`selected`:``}>Not Enrolled</option>
                    </select>
                    <select id="um-filter-online" style="padding: 8px 12px; background: rgba(0,0,0,0.3); border: 1px solid var(--border-color); color: var(--text-primary); border-radius: 4px; cursor: pointer;">
                        <option value="ALL" ${o.onlineFilter===`ALL`?`selected`:``}>Any Connection</option>
                        <option value="ONLINE" ${o.onlineFilter===`ONLINE`?`selected`:``}>Online</option>
                        <option value="OFFLINE" ${o.onlineFilter===`OFFLINE`?`selected`:``}>Offline</option>
                    </select>
                </div>

                <div style="overflow-x: auto;">
                    <table style="width: 100%; border-collapse: collapse; text-align: left; min-width: 1000px;">
                        <thead>
                            <tr style="border-bottom: 2px solid var(--border-color); color: var(--text-secondary);">
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('name')">User ${n(`name`)}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('atlas_person_id')">Person ID ${n(`atlas_person_id`)}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('role')">Role ${n(`role`)}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('enabled')">Account Status ${n(`enabled`)}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('face_enrollment_status')">Biometrics ${n(`face_enrollment_status`)}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('online')">Session ${n(`online`)}</th>
                                <th style="padding: 12px 10px; cursor: pointer; user-select: none;" onclick="window.sortUsers('last_access')">Last Access ${n(`last_access`)}</th>
                                <th style="padding: 12px 10px;">Last Location</th>
                                <th style="padding: 12px 10px;">Risk Level</th>
                                <th style="padding: 12px 10px;">Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${t.length>0?t:`<tr><td colspan="10" style="text-align: center; padding: 30px; color: var(--text-secondary);">No users found matching criteria.</td></tr>`}
                        </tbody>
                    </table>
                </div>
                <div style="margin-top: 15px; font-size: 0.85em; color: var(--text-secondary); text-align: right;">
                    Showing ${e.length} of ${a.length} total users
                </div>
            </div>
        `,document.getElementById(`um-search`).addEventListener(`input`,e=>{o.searchQuery=e.target.value,p()}),document.getElementById(`um-filter-role`).addEventListener(`change`,e=>{o.roleFilter=e.target.value,p()}),document.getElementById(`um-filter-status`).addEventListener(`change`,e=>{o.statusFilter=e.target.value,p()}),document.getElementById(`um-filter-bio`).addEventListener(`change`,e=>{o.bioFilter=e.target.value,p()}),document.getElementById(`um-filter-online`).addEventListener(`change`,e=>{o.onlineFilter=e.target.value,p()}),document.getElementById(`btn-refresh-users`).addEventListener(`click`,()=>{s()}),document.activeElement&&document.activeElement.id===`um-search`){let e=document.getElementById(`um-search`),t=e.value;e.focus(),e.value=``,e.value=t}};window.toggleUserStatus=c,window.enrollUserFace=l,window.sortUsers=u,window.viewUserDetails=async e=>{if(!e)return;let t=document.getElementById(`user-intelligence-panel`);t||(t=document.createElement(`div`),t.id=`user-intelligence-panel`,t.className=`glass-panel`,t.style.cssText=`
                position: fixed; top: 0; right: 0; width: 450px; height: 100vh;
                background: rgba(10, 15, 25, 0.95); border-left: 1px solid var(--border-color);
                box-shadow: -5px 0 25px rgba(0,0,0,0.8); z-index: 1000;
                transform: translateX(100%); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                overflow-y: auto; padding: 30px; color: var(--text-primary);
            `,document.body.appendChild(t)),setTimeout(()=>t.style.transform=`translateX(0)`,10),t.innerHTML=`<div style="text-align:center; padding: 50px; color: var(--accent-color); font-family: var(--font-heading);"><i class="fas fa-circle-notch fa-spin"></i> FETCHING INTELLIGENCE...</div>`;try{let[r,i]=await Promise.all([fetch(`/api/v1/admin/people/${e}/profile`,{headers:{Authorization:`Bearer ${n}`}}),fetch(`/api/v1/admin/people/${e}/activity?limit=10`,{headers:{Authorization:`Bearer ${n}`}})]);if(!r.ok)throw Error(`Profile not found`);let a=await r.json(),o=i.ok?await i.json():{items:[]},s=null;if(a.has_latest_snapshot)try{let t=await fetch(`/api/v1/admin/people/${e}/snapshots?include_image=true`,{headers:{Authorization:`Bearer ${n}`}});if(t.ok){let e=await t.json();e.snapshots&&e.snapshots.length>0&&(s=e.snapshots[0].image_base64)}}catch{}let c=e=>e?new Date(e*1e3).toLocaleString():`Unavailable`;t.innerHTML=`
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px; border-bottom: 1px solid var(--border-color); padding-bottom: 15px;">
                    <h2 style="margin:0; font-family: var(--font-heading); color: var(--accent-color);"><i class="fas fa-id-card"></i> User Intelligence</h2>
                    <button class="btn-secondary btn-sm" onclick="document.getElementById('user-intelligence-panel').style.transform = 'translateX(100%)'"><i class="fas fa-times"></i> Close</button>
                </div>
                
                <!-- SECURITY RISK -->
                <div style="margin-bottom: 30px; background: rgba(0,0,0,0.4); padding: 15px; border-radius: 8px; border: 1px solid ${a.risk_level===`HIGH`?`var(--accent-danger)`:a.risk_level===`MEDIUM`?`var(--warning-color)`:`var(--success-color)`}; box-shadow: 0 0 15px ${a.risk_level===`HIGH`?`rgba(255, 68, 68, 0.1)`:`transparent`};">
                    <div style="font-weight: bold; font-size: 1.1em; margin-bottom: 8px; color: ${a.risk_level===`HIGH`?`var(--accent-danger)`:a.risk_level===`MEDIUM`?`var(--warning-color)`:`var(--success-color)`};">
                        <i class="fas ${a.risk_level===`HIGH`?`fa-shield-alt`:a.risk_level===`MEDIUM`?`fa-exclamation-triangle`:`fa-shield-check`}"></i> RISK LEVEL: ${a.risk_level||`LOW`}
                    </div>
                    <ul style="margin: 0; padding-left: 25px; color: var(--text-primary); font-size: 0.9em; line-height: 1.5;">
                        ${(a.risk_reasons||[`No data`]).map(e=>`<li>${e}</li>`).join(``)}
                    </ul>
                </div>

                <!-- 1. IDENTITY -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">IDENTITY</h4>
                    <div style="display: flex; gap: 20px; align-items: center;">
                        ${s?`<img src="data:image/jpeg;base64,${s}" style="width: 80px; height: 80px; border-radius: 8px; border: 1px solid var(--accent-color); object-fit: cover; box-shadow: 0 0 10px rgba(0,208,255,0.2);" />`:`<div style="width: 80px; height: 80px; border-radius: 8px; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-color);"><i class="fas fa-user" style="font-size: 30px; color: var(--text-secondary);"></i></div>`}
                        <div>
                            <div style="font-size: 1.2em; font-weight: bold; color: var(--text-primary);">${a.display_name||`Unknown`}</div>
                            <div style="color: var(--text-secondary);">@${a.username||`Unavailable`}</div>
                            <div style="font-family: monospace; font-size: 0.85em; margin-top: 5px; color: var(--accent-color);">${a.person_id}</div>
                            <div style="margin-top: 8px; display: flex; gap: 8px;">
                                <span class="status-badge" style="background: rgba(255,255,255,0.1);">${a.role||`Unavailable`}</span>
                                <span class="status-badge ${a.account_enabled?`success`:`danger`}">${a.account_enabled?`ACTIVE`:`DISABLED`}</span>
                            </div>
                        </div>
                    </div>
                    <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 15px;">Created: ${c(a.created_at)}</div>
                </div>
                
                <!-- 2. BIOMETRIC PROFILE -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">BIOMETRIC PROFILE</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.9em;">
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Status</span> <span class="status-badge ${a.face_enrollment_status===`ENROLLED`?`success`:`warning`}" style="margin-top:4px;">${a.face_enrollment_status||`Unavailable`}</span></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Templates</span> <div style="margin-top:4px; font-weight:bold;">${a.template_count||0}</div></div>
                        <div style="grid-column: span 2;"><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Enrolled</span> <div style="margin-top:4px;">${c(a.enrolled_at)}</div></div>
                        <div style="grid-column: span 2;"><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Last Verification</span> <div style="margin-top:4px;">${c(a.last_biometric_verification)}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Result</span> <div style="margin-top:4px; font-weight:bold; color:${a.latest_verification_result===`SUCCESS`?`var(--success-color)`:a.latest_verification_result?`var(--accent-danger)`:`var(--text-primary)`}">${a.latest_verification_result||`None`}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Confidence Score</span> <div style="margin-top:4px;">${a.latest_verification_score?a.latest_verification_score.toFixed(4):`N/A`}</div></div>
                    </div>
                </div>
                
                <!-- 3. LIVE ACCESS STATUS -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">LIVE ACCESS STATUS</h4>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.9em;">
                        <div>
                            ${a.online?`<div style="color:var(--success-color); font-weight: bold; margin-top: 4px;"><i class="fas fa-circle" style="text-shadow: 0 0 5px var(--success-color);"></i> Online</div>`:`<div style="color:var(--text-secondary); margin-top: 4px;"><i class="far fa-circle"></i> Offline</div>`}
                        </div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Session ID</span> <div style="margin-top:4px; font-family: monospace;">${a.current_session_id?a.current_session_id.substring(0,8)+`...`:`None`}</div></div>
                        <div style="grid-column: span 2;"><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Login Time</span> <div style="margin-top:4px;">${c(a.session_started_at)}</div></div>
                    </div>
                </div>
                
                <!-- 4. LAST ACCESS -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">LAST ACCESS</h4>
                    <div style="display: grid; grid-template-columns: 1fr; gap: 12px; font-size: 0.9em;">
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Timestamp</span> <div style="margin-top:4px;">${c(a.last_access_timestamp||a.last_login)}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">IP Address</span> <div style="margin-top:4px; font-family: monospace;">${a.last_access_ip||`Unavailable`}</div></div>
                        <div><span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Device Info</span> <div style="margin-top:4px;">${a.last_access_device||`Unavailable`}</div></div>
                        
                        <div>
                            <span style="color:var(--text-secondary); display:block; font-size: 0.85em;">Location</span>
                            <div style="margin-top: 8px;">
                                ${a.last_access_location?`
                                    <div style="margin-bottom: 8px;">
                                        <span style="color:var(--accent-color);"><i class="fas fa-map-marker-alt"></i> ${a.last_access_location.latitude.toFixed(4)}, ${a.last_access_location.longitude.toFixed(4)}</span>
                                        <span style="color:var(--text-secondary); font-size: 0.9em; margin-left: 10px;">(Accuracy: ${a.last_access_location.accuracy}m)</span>
                                    </div>
                                    <div style="width: 100%; height: 200px; border-radius: 8px; overflow: hidden; border: 1px solid var(--border-color);">
                                        <iframe width="100%" height="100%" frameborder="0" scrolling="no" marginheight="0" marginwidth="0" 
                                            src="https://www.openstreetmap.org/export/embed.html?bbox=${a.last_access_location.longitude-.01}%2C${a.last_access_location.latitude-.01}%2C${a.last_access_location.longitude+.01}%2C${a.last_access_location.latitude+.01}&amp;layer=mapnik&amp;marker=${a.last_access_location.latitude}%2C${a.last_access_location.longitude}" 
                                            style="border: none; filter: invert(90%) hue-rotate(180deg) contrast(80%); pointer-events: auto;">
                                        </iframe>
                                    </div>
                                    `:a.location_permission===`denied`?`<span style="color:var(--accent-danger);"><i class="fas fa-ban"></i> Location permission denied</span>`:`<span style="color:var(--text-secondary);"><i class="fas fa-eye-slash"></i> Location not available</span>`}
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- 5. VERIFICATION EVIDENCE -->
                <div style="margin-bottom: 30px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">VERIFICATION EVIDENCE</h4>
                    ${s?`
                        <div style="display: flex; gap: 15px; align-items: flex-start; background: rgba(0,0,0,0.3); padding: 10px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05);">
                            <img src="data:image/jpeg;base64,${s}" style="width: 100px; height: 100px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border-color);" />
                            <div style="font-size: 0.9em; flex: 1;">
                                <div style="margin-bottom: 8px;"><span style="color:var(--text-secondary); font-size: 0.85em; display:block;">Captured At</span>${c(a.latest_verification_timestamp)}</div>
                                <div><span style="color:var(--text-secondary); font-size: 0.85em; display:block; margin-bottom: 4px;">Status</span><span class="status-badge ${a.latest_verification_result===`SUCCESS`?`success`:`danger`}">${a.latest_verification_result}</span></div>
                            </div>
                        </div>
                    `:`<div style="color: var(--text-secondary); font-style: italic; font-size: 0.9em;">No verification evidence captured.</div>`}
                </div>
                
                <!-- 6. ACTIVITY TIMELINE -->
                <div style="margin-bottom: 25px;">
                    <h4 style="color: var(--text-secondary); margin-bottom: 15px; border-bottom: 1px dashed rgba(255,255,255,0.1); padding-bottom: 5px; font-size: 0.85em; letter-spacing: 1px;">ACTIVITY TIMELINE</h4>
                    <div style="position: relative; padding-left: 15px; border-left: 2px solid rgba(255,255,255,0.1); margin-left: 5px;">
                        ${o.items&&o.items.length>0?o.items.map(e=>`
                            <div style="margin-bottom: 20px; position: relative;">
                                <div style="position: absolute; left: -21px; top: 5px; width: 10px; height: 10px; border-radius: 50%; background: ${e.access_result===`SUCCESS`?`var(--accent-color)`:`var(--accent-danger)`}; box-shadow: 0 0 8px ${e.access_result===`SUCCESS`?`var(--accent-color)`:`var(--accent-danger)`}; border: 2px solid var(--bg-color);"></div>
                                <div style="font-weight: bold; color: var(--text-primary); font-size: 0.95em;">[${e.event_type.replace(/_/g,` `)}]</div>
                                <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 2px;">${c(e.timestamp)}</div>
                                ${e.gps_latitude?`<div style="font-size: 0.85em; color: var(--accent-color); margin-top: 4px;"><i class="fas fa-map-marker-alt"></i> Location captured</div>`:``}
                                ${e.access_result&&e.access_result!==`SUCCESS`?`<div style="font-size: 0.85em; color: var(--accent-danger); margin-top: 4px;">${e.access_result} ${e.failure_category?`(${e.failure_category})`:``}</div>`:``}
                            </div>
                        `).join(``):`<div style="color: var(--text-secondary); font-style: italic; font-size: 0.9em;">No activity yet.</div>`}
                    </div>
                </div>
            `}catch(e){t.innerHTML=`
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px;">
                    <h2 style="margin:0; color: var(--accent-danger);"><i class="fas fa-exclamation-triangle"></i> Error</h2>
                    <button class="btn-secondary btn-sm" onclick="document.getElementById('user-intelligence-panel').style.transform = 'translateX(100%)'">Close</button>
                </div>
                <div style="color: var(--accent-danger); padding: 20px; background: rgba(255,0,0,0.1); border-radius: 8px;">${e.message}</div>
            `}},s()}function p(e,t,n){let r=document.getElementById(`app`);r.innerHTML=`
        <div class="dashboard-wrapper">
            ${o(e,`overview`)}
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
    `,document.getElementById(`btn-logout`).addEventListener(`click`,()=>{n()});async function i(){try{let e=await fetch(`/api/v1/dashboard`,{method:`GET`,headers:{Authorization:`Bearer ${t}`}});if(!e.ok)throw Error(`Failed to load dashboard statistics.`);let n=await e.json(),r=document.getElementById(`dashboard-content`);r.innerHTML=`
                <div class="grid-col">
                    ${l(n.system_status,n.role)}
                    <div style="margin-top: 25px;"></div>
                    ${s(n.devices)}
                </div>
                <div class="grid-col">
                    ${c(n.recent_events,n.alerts)}
                </div>
                
                <!-- Admin specific operations card -->
                <div id="user-management-container" style="grid-column: span 2; margin-top: 20px;"></div>
            `,f(`user-management-container`,t,i)}catch(e){document.getElementById(`dashboard-content`).innerHTML=`
                <div style="grid-column: span 2; text-align: center; color: var(--accent-danger); padding: 50px 0;">
                    ${e.message||`Failed to load telemetry.`}
                </div>
            `}}i()}console.log(`[ATLAS FRONTEND] index.js loaded`);var m={token:localStorage.getItem(`atlas_session_token`)||null,role:localStorage.getItem(`atlas_session_role`)||null};async function h(){if(console.log(`[ATLAS FRONTEND] checkSession started`),!m.token){console.log(`[ATLAS FRONTEND] no token, calling showLogin`),g();return}try{let e=await fetch(`/api/v1/auth/session`,{headers:{Authorization:`Bearer ${m.token}`}});e.ok?_((await e.json()).role,m.token):(y(),g())}catch{y(),g()}}function g(){a((e,t)=>{localStorage.setItem(`atlas_session_token`,t),localStorage.setItem(`atlas_session_role`,e),m.token=t,m.role=e,_(e,t)})}function _(e,t){e.toUpperCase()===`ADMIN`?p(e,t,v):d(e,t,v)}async function v(){if(m.token)try{await fetch(`/api/v1/auth/logout`,{method:`POST`,headers:{Authorization:`Bearer ${m.token}`}})}catch(e){console.error(`Logout API request failed:`,e)}y(),g()}function y(){localStorage.removeItem(`atlas_session_token`),localStorage.removeItem(`atlas_session_role`),m.token=null,m.role=null}h();
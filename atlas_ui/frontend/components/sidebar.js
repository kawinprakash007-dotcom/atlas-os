export function renderSidebar(role, activeTab = "overview") {
    const isAdmin = role.toUpperCase() === "ADMIN";
    
    return `
        <div class="sidebar">
            <div class="sidebar-header-wrapper">
                <div class="sidebar-header">
                    <h2 class="sidebar-title">ATLAS OS</h2>
                    <span class="sidebar-subtitle">Autonomous System</span>
                </div>
                <ul class="sidebar-menu">
                    <li class="menu-item">
                        <a class="menu-link ${activeTab === 'overview' ? 'active' : ''}" id="nav-overview">
                            System Overview
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${activeTab === 'devices' ? 'active' : ''}" id="nav-devices">
                            Devices
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${activeTab === 'events' ? 'active' : ''}" id="nav-events">
                            Events & Alerts
                        </a>
                    </li>
                    ${isAdmin ? `
                    <li class="menu-item">
                        <a class="menu-link ${activeTab === 'users' ? 'active' : ''}" id="nav-users">
                            User Management
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${activeTab === 'security' ? 'active' : ''}" id="nav-security">
                            Security Logs
                        </a>
                    </li>
                    <li class="menu-item">
                        <a class="menu-link ${activeTab === 'config' ? 'active' : ''}" id="nav-config">
                            System Configuration
                        </a>
                    </li>
                    ` : ''}
                </ul>
            </div>
            <div class="sidebar-footer">
                <div class="user-badge">${role} Session Active</div>
                <button class="btn-primary" id="btn-logout" style="padding: 10px; font-size: 0.8rem;">
                    Disconnect
                </button>
            </div>
        </div>
    `;
}

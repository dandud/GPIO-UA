const state = {
    authCredentials: null,
    config: null,
    health: null,
    ws: null
};

// DOM Elements
const authOverlay = document.getElementById('auth-overlay');
const mainUI = document.getElementById('main-ui');
const authTitle = document.getElementById('auth-title');
const authSubtitle = document.getElementById('auth-subtitle');
const authForm = document.getElementById('auth-form');
const authPassword = document.getElementById('auth-password');
const authError = document.getElementById('auth-error');

const navLinks = document.querySelectorAll('.nav-links li');
const views = document.querySelectorAll('.view');
const healthStatusText = document.getElementById('health-status-text');
const statusIndicator = document.querySelector('.status-indicator');

// Setup Navigation
navLinks.forEach(link => {
    link.addEventListener('click', (e) => {
        navLinks.forEach(l => l.classList.remove('active'));
        e.currentTarget.classList.add('active');
        
        const targetId = e.currentTarget.getAttribute('data-target');
        views.forEach(v => v.classList.remove('active'));
        document.getElementById(targetId).classList.add('active');
    });
});

// Fetch wrapper with auth
async function apiFetch(endpoint, options = {}) {
    if (state.authCredentials) {
        options.headers = {
            ...options.headers,
            'Authorization': 'Basic ' + btoa('admin:' + state.authCredentials)
        };
    }
    const res = await fetch(`/api${endpoint}`, options);
    if (res.status === 401) {
        showAuth();
        throw new Error("Unauthorized");
    }
    return res;
}

// Initialization
async function init() {
    try {
        const res = await fetch('/api/health');
        state.health = await res.json();
        
        if (state.health.setup_required) {
            showSetup();
            return;
        }
        
        if (state.health.auth_enabled) {
            showAuth();
            return;
        }

        // No auth required
        await loadApp();
    } catch (e) {
        console.error("Init error", e);
    }
}

function showSetup() {
    authOverlay.classList.remove('hidden');
    mainUI.classList.add('hidden');
    authTitle.textContent = "First-Boot Setup";
    authSubtitle.textContent = "Set an admin password to secure GPIO-UA";
    
    authForm.onsubmit = async (e) => {
        e.preventDefault();
        try {
            const res = await fetch('/api/setup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: authPassword.value })
            });
            if (res.ok) {
                state.authCredentials = authPassword.value;
                await loadApp();
            } else {
                authError.textContent = "Setup failed.";
            }
        } catch (e) {
            authError.textContent = e.message;
        }
    };
}

function showAuth() {
    authOverlay.classList.remove('hidden');
    mainUI.classList.add('hidden');
    authTitle.textContent = "Login";
    authSubtitle.textContent = "Enter your admin password.";
    authPassword.value = '';
    
    authForm.onsubmit = async (e) => {
        e.preventDefault();
        state.authCredentials = authPassword.value;
        try {
            await apiFetch('/check-auth');
            await loadApp();
        } catch (e) {
            authError.textContent = "Invalid password.";
            state.authCredentials = null;
        }
    };
}

async function loadApp() {
    authOverlay.classList.add('hidden');
    mainUI.classList.remove('hidden');
    
    await fetchConfig();
    setupWebSocket();
    startHealthPoll();
}

// Configuration logic
async function fetchConfig() {
    const res = await apiFetch('/config');
    state.config = await res.json();
    populateConfigUI();
}

function populateConfigUI() {
    document.getElementById('config-port').value = state.config.web_port || 8080;
    document.getElementById('config-auth-toggle').checked = state.config.auth_enabled || false;
    
    const tbody = document.querySelector('#sensors-table tbody');
    tbody.innerHTML = '';
    (state.config.sensors || []).forEach((sensor, index) => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${sensor.tag_name}</td>
            <td>${sensor.pin}</td>
            <td>${sensor.type.toUpperCase()}</td>
            <td><button class="btn-danger" onclick="removeSensor(${index})">Remove</button></td>
        `;
        tbody.appendChild(tr);
    });
}

document.getElementById('network-config-form').onsubmit = async (e) => {
    e.preventDefault();
    const payload = {
        web_port: parseInt(document.getElementById('config-port').value),
        auth_enabled: document.getElementById('config-auth-toggle').checked
    };
    alert("Updating network config... OPC-UA Server restarting. If port changed, refresh browser at new port.");
    await apiFetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
};

document.getElementById('add-sensor-form').onsubmit = async (e) => {
    e.preventDefault();
    const newSensor = {
        tag_name: document.getElementById('new-sensor-tag').value,
        pin: parseInt(document.getElementById('new-sensor-pin').value),
        type: document.getElementById('new-sensor-type').value
    };
    const sensors = [...(state.config.sensors || []), newSensor];
    
    await apiFetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sensors })
    });
    
    // Clear form and refetch
    e.target.reset();
    await fetchConfig();
};

window.removeSensor = async (index) => {
    const sensors = [...state.config.sensors];
    sensors.splice(index, 1);
    await apiFetch('/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sensors })
    });
    await fetchConfig();
};

// Dashboard & WebSockets
function setupWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    state.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
    
    state.ws.onopen = () => {
        statusIndicator.classList.remove('offline');
        statusIndicator.classList.add('online');
        healthStatusText.textContent = "Connected";
    };
    
    state.ws.onclose = () => {
        statusIndicator.classList.remove('online');
        statusIndicator.classList.add('offline');
        healthStatusText.textContent = "Disconnected (Reconnecting...)";
        setTimeout(setupWebSocket, 3000);
    };
    
    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.type === 'tag_update') {
            updateWatchlist(data);
        }
    };
}

const activeTags = new Map();
function updateWatchlist(data) {
    activeTags.set(data.tag, data);
    const tbody = document.querySelector('#watchlist-table tbody');
    tbody.innerHTML = '';
    
    for (const [tag, info] of activeTags.entries()) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${tag}</strong></td>
            <td style="color: ${info.value ? 'var(--success)' : 'var(--text-main)'}">${info.value}</td>
            <td>${info.quality}</td>
        `;
        tbody.appendChild(tr);
    }
}

function startHealthPoll() {
    setInterval(async () => {
        try {
            const res = await fetch('/api/health');
            const data = await res.json();
            
            document.getElementById('cpu-bar').style.width = `${data.cpu_usage}%`;
            document.getElementById('cpu-text').textContent = `${data.cpu_usage.toFixed(1)}%`;
            
            document.getElementById('mem-bar').style.width = `${data.memory_usage}%`;
            document.getElementById('mem-text').textContent = `${data.memory_usage.toFixed(1)}%`;
            
            document.getElementById('uptime-text').textContent = formatUptime(data.uptime);
        } catch (e) {
            console.error("Health poll failed");
        }
    }, 5000);
}

function formatUptime(seconds) {
    const d = Math.floor(seconds / (3600*24));
    const h = Math.floor(seconds % (3600*24) / 3600);
    const m = Math.floor(seconds % 3600 / 60);
    return `${d}d ${h}h ${m}m`;
}

// Start app
init();

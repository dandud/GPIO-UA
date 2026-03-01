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
    renderPinMap();
    setupWebSocket();
    startHealthPoll();
    startLogPoll();
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
            <td>${sensor.gpio}</td>
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
        gpio: parseInt(document.getElementById('new-sensor-gpio').value),
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
    renderPinMap(); // refresh pin map after sensor change
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
    renderPinMap();
};

// ===========================
//  Raspberry Pi 40-Pin Map
// ===========================

// Full 40-pin header definition (physical pin 1-40)
// Each entry: [physicalPin, label, type, bcmGpio]
// type: '3v3', '5v', 'gnd', 'gpio', 'i2c', 'spi', 'uart', 'eeprom', 'pcm'
const PIN_LAYOUT = [
    // Row 1: physical pins 1 (left) – 2 (right)
    [1, '3V3', '3v3', null], [2, '5V', '5v', null],
    [3, 'GPIO2', 'i2c', 2], [4, '5V', '5v', null],
    [5, 'GPIO3', 'i2c', 3], [6, 'GND', 'gnd', null],
    [7, 'GPIO4', 'gpio', 4], [8, 'GPIO14', 'uart', 14],
    [9, 'GND', 'gnd', null], [10, 'GPIO15', 'uart', 15],
    [11, 'GPIO17', 'gpio', 17], [12, 'GPIO18', 'pcm', 18],
    [13, 'GPIO27', 'gpio', 27], [14, 'GND', 'gnd', null],
    [15, 'GPIO22', 'gpio', 22], [16, 'GPIO23', 'gpio', 23],
    [17, '3V3', '3v3', null], [18, 'GPIO24', 'gpio', 24],
    [19, 'GPIO10', 'spi', 10], [20, 'GND', 'gnd', null],
    [21, 'GPIO9', 'spi', 9], [22, 'GPIO25', 'gpio', 25],
    [23, 'GPIO11', 'spi', 11], [24, 'GPIO8', 'spi', 8],
    [25, 'GND', 'gnd', null], [26, 'GPIO7', 'spi', 7],
    [27, 'ID_SD', 'eeprom', null], [28, 'ID_SC', 'eeprom', null],
    [29, 'GPIO5', 'gpio', 5], [30, 'GND', 'gnd', null],
    [31, 'GPIO6', 'gpio', 6], [32, 'GPIO12', 'gpio', 12],
    [33, 'GPIO13', 'gpio', 13], [34, 'GND', 'gnd', null],
    [35, 'GPIO19', 'pcm', 19], [36, 'GPIO16', 'gpio', 16],
    [37, 'GPIO26', 'gpio', 26], [38, 'GPIO20', 'pcm', 20],
    [39, 'GND', 'gnd', null], [40, 'GPIO21', 'pcm', 21],
];

// Build a lookup: BCM GPIO number → configured sensor info
function buildPinSensorMap() {
    const map = {};
    (state.config?.sensors || []).forEach(s => {
        map[s.gpio] = s;
    });
    return map;
}

const pinElements = {}; // physical pin number → DOM element

function renderPinMap() {
    const container = document.getElementById('pin-header');
    const tooltip = document.getElementById('pin-tooltip');
    container.innerHTML = '';

    const sensorMap = buildPinSensorMap();

    // Render 20 rows × 2 pins each
    for (let row = 0; row < 20; row++) {
        const leftPin = PIN_LAYOUT[row * 2];
        const rightPin = PIN_LAYOUT[row * 2 + 1];

        // Left label
        const leftLabel = document.createElement('span');
        leftLabel.className = 'pin-row-label';
        leftLabel.textContent = leftPin[1];
        container.appendChild(leftLabel);

        // Left pin dot
        const leftDot = createPinDot(leftPin, sensorMap, tooltip);
        container.appendChild(leftDot);

        // Center gap
        const gap = document.createElement('span');
        gap.className = 'pin-gap-col';
        container.appendChild(gap);

        // Right pin dot
        const rightDot = createPinDot(rightPin, sensorMap, tooltip);
        container.appendChild(rightDot);

        // Right label
        const rightLabel = document.createElement('span');
        rightLabel.className = 'pin-row-label right';
        rightLabel.textContent = rightPin[1];
        container.appendChild(rightLabel);
    }

    // Legend
    const parent = container.parentElement;
    let legend = parent.querySelector('.pin-legend');
    if (!legend) {
        legend = document.createElement('div');
        legend.className = 'pin-legend';
        legend.innerHTML = [
            ['pin-power-3v3', '3.3V'],
            ['pin-power-5v', '5V'],
            ['pin-gnd', 'GND'],
            ['pin-gpio', 'GPIO'],
            ['pin-i2c', 'I2C'],
            ['pin-spi', 'SPI'],
            ['pin-uart', 'UART'],
        ].map(([cls, name]) =>
            `<span class="legend-item"><span class="legend-dot ${cls}"></span>${name}</span>`
        ).join('');
        parent.appendChild(legend);
    }
}

function createPinDot(pinDef, sensorMap, tooltip) {
    const [phys, label, type, bcm] = pinDef;
    const dot = document.createElement('div');
    dot.className = `pin-dot pin-${type === '3v3' ? 'power-3v3' : type === '5v' ? 'power-5v' : type}`;
    dot.textContent = phys;
    dot.dataset.phys = phys;
    dot.dataset.bcm = bcm ?? '';
    dot.dataset.label = label;
    dot.dataset.type = type;

    // Highlight if configured
    const sensor = bcm !== null ? sensorMap[bcm] : null;
    if (sensor) {
        dot.classList.add('pin-active');
        dot.dataset.tag = sensor.tag_name;
    }

    pinElements[phys] = dot;

    // Tooltip events
    dot.addEventListener('mouseenter', (e) => {
        const sensor = bcm !== null ? buildPinSensorMap()[bcm] : null;
        const liveVal = activeTags.get(sensor?.tag_name);

        let html = `<div class="tt-pin">Pin ${phys} &middot; ${label}</div>`;
        if (bcm !== null) html += `<div class="tt-func">BCM ${bcm} &middot; ${type.toUpperCase()}</div>`;
        if (sensor) {
            html += `<div class="tt-tag">Tag: ${sensor.tag_name}</div>`;
            html += `<div class="tt-value">Value: ${liveVal ? liveVal.value : '—'}</div>`;
        }
        tooltip.innerHTML = html;
        tooltip.classList.add('visible');

        const rect = dot.getBoundingClientRect();
        const containerRect = dot.closest('.pin-map-container').getBoundingClientRect();
        tooltip.style.left = (rect.left - containerRect.left + rect.width / 2) + 'px';
        tooltip.style.top = (rect.top - containerRect.top - tooltip.offsetHeight - 8) + 'px';
    });

    dot.addEventListener('mouseleave', () => {
        tooltip.classList.remove('visible');
    });

    return dot;
}

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
            updatePinMapLive(data);
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

function updatePinMapLive(data) {
    // Find which pin has this tag and update its visual state
    const sensors = state.config?.sensors || [];
    const sensor = sensors.find(s => s.tag_name === data.tag);
    if (!sensor) return;

    // Find the physical pin for this BCM GPIO
    for (const [phys, label, type, bcm] of PIN_LAYOUT) {
        if (bcm === sensor.gpio) {
            const dot = pinElements[phys];
            if (dot) {
                dot.classList.toggle('pin-value-high', !!data.value);
            }
            break;
        }
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
    const d = Math.floor(seconds / (3600 * 24));
    const h = Math.floor(seconds % (3600 * 24) / 3600);
    const m = Math.floor(seconds % 3600 / 60);
    return `${d}d ${h}h ${m}m`;
}

// Log Viewer
function startLogPoll() {
    const logWindow = document.getElementById('log-window');
    setInterval(async () => {
        try {
            const res = await fetch('/api/logs');
            const data = await res.json();
            logWindow.innerHTML = '';
            (data.logs || []).forEach(line => {
                const div = document.createElement('div');
                div.textContent = line;
                logWindow.appendChild(div);
            });
            logWindow.scrollTop = logWindow.scrollHeight;
        } catch (e) {
            console.error("Log poll failed");
        }
    }, 3000);
}

// Start app
init();

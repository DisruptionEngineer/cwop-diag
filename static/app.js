// CWOP-Diag Dashboard — Frontend Logic

let pollInterval = null;
let isAnalyzing = false;

// --- Initialization ---

document.addEventListener('DOMContentLoaded', () => {
    checkStatus();
    pollInterval = setInterval(pollSnapshot, 2000);
    pollSnapshot();
});

// --- API Calls ---

async function checkStatus() {
    try {
        const resp = await fetch('/api/status');
        const data = await resp.json();
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        const mode = document.getElementById('modeLabel');

        if (data.demo_mode) {
            dot.className = 'status-dot connected';
            text.textContent = 'Demo Mode';
            mode.textContent = 'DEMO';
            mode.className = 'mode-badge';
        } else if (data.obd_connected) {
            dot.className = 'status-dot connected';
            text.textContent = 'Connected';
            mode.textContent = 'LIVE';
            mode.className = 'mode-badge live';
        } else {
            dot.className = 'status-dot error';
            text.textContent = 'No Vehicle';
            mode.textContent = 'OFFLINE';
            mode.className = 'mode-badge';
        }
    } catch (e) {
        document.getElementById('statusDot').className = 'status-dot error';
        document.getElementById('statusText').textContent = 'Server Error';
    }
}

async function pollSnapshot() {
    try {
        const resp = await fetch('/api/snapshot');
        const data = await resp.json();
        renderSensors(data.sensors);
        renderDTCs(data.dtcs);
        renderBudget(data.budget);
    } catch (e) {
        // Server not reachable
    }
}

async function runDiagnosis() {
    if (isAnalyzing) return;
    isAnalyzing = true;

    const btn = document.getElementById('diagnoseBtn');
    const output = document.getElementById('aiOutput');
    const meta = document.getElementById('aiMeta');

    btn.disabled = true;
    btn.textContent = 'Thinking...';
    output.innerHTML = '<div class="thinking">Analyzing DTCs and sensor data...</div>';
    meta.textContent = '';

    try {
        const resp = await fetch('/api/diagnose', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        const data = await resp.json();
        output.textContent = data.response;
        const secs = (data.duration_ms / 1000).toFixed(1);
        meta.textContent = `${data.tokens} tokens | ${secs}s`;
        if (data.budget) renderBudget(data.budget);
    } catch (e) {
        output.textContent = 'Error: Could not reach LLM. Is the server running?';
    }

    btn.disabled = false;
    btn.textContent = 'Analyze';
    isAnalyzing = false;
}

// --- Renderers ---

function renderSensors(sensors) {
    const grid = document.getElementById('sensorGrid');
    if (!sensors) return;

    // Key sensors to display (subset for 720x720)
    const keys = [
        'RPM', 'Coolant Temp', 'Engine Load', 'Throttle',
        'STFT B1', 'LTFT B1', 'STFT B2', 'LTFT B2',
        'MAF', 'Intake Temp', 'O2 B1S1', 'Timing Adv'
    ];

    grid.innerHTML = keys.map(key => {
        const val = sensors[key] || '--';
        const cls = getSensorClass(key, val);
        return `<div class="sensor-cell">
            <div class="sensor-label">${key}</div>
            <div class="sensor-value ${cls}">${val}</div>
        </div>`;
    }).join('');
}

function getSensorClass(key, val) {
    // Highlight abnormal values
    const num = parseFloat(val);
    if (isNaN(num)) return '';

    if (key === 'Coolant Temp' && num > 105) return 'alert';
    if (key === 'Coolant Temp' && num > 95) return 'warn';
    if (key.includes('LTFT') && Math.abs(num) > 10) return 'warn';
    if (key.includes('LTFT') && Math.abs(num) > 15) return 'alert';
    if (key.includes('STFT') && Math.abs(num) > 15) return 'warn';
    if (key.includes('STFT') && Math.abs(num) > 25) return 'alert';
    if (key === 'RPM' && num > 5000) return 'warn';
    if (key === 'RPM' && num > 6500) return 'alert';
    return '';
}

function renderDTCs(dtcs) {
    const list = document.getElementById('dtcList');
    const count = document.getElementById('dtcCount');

    if (!dtcs || dtcs.length === 0) {
        list.innerHTML = '<div class="empty-state">No trouble codes detected</div>';
        count.textContent = '0';
        count.className = 'badge clear';
        return;
    }

    count.textContent = dtcs.length;
    count.className = 'badge';

    list.innerHTML = dtcs.map(dtc => {
        const causes = dtc.common_causes.slice(0, 3).join(', ');
        return `<div class="dtc-item">
            <span class="dtc-code ${dtc.severity}">${dtc.code}</span>
            <div style="flex:1">
                <div class="dtc-desc">${dtc.desc}</div>
                ${causes ? `<div class="dtc-causes">${causes}</div>` : ''}
            </div>
            <span class="severity-tag ${dtc.severity}">${dtc.severity}</span>
        </div>`;
    }).join('');
}

function renderBudget(budget) {
    if (!budget) return;
    const fill = document.getElementById('budgetFill');
    const text = document.getElementById('budgetText');
    const pct = budget.utilization;

    fill.style.width = pct + '%';
    fill.className = 'budget-fill' +
        (pct > 80 ? ' full' : pct > 60 ? ' warn' : '');
    text.textContent = pct + '%';
}

// CWOP-Diag Dashboard — Frontend Logic (Tech Screen)

let pollInterval = null;
let isAnalyzing = false;
let estimateSent = false;

// ─── Initialization ───

document.addEventListener('DOMContentLoaded', () => {
    checkStatus();
    pollInterval = setInterval(pollSnapshot, 2000);
    pollSnapshot();

    // Live-update estimate total as inputs change
    ['estDiag', 'estParts', 'estLabor'].forEach(id => {
        document.getElementById(id).addEventListener('input', updateEstTotal);
    });
});

// ─── API Calls ───

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

        // Show vehicle info if available
        if (data.vehicle_info && data.vin) {
            renderVehicleBar(data.vehicle_info, data.vin);
        }

        // Show health score if available
        if (data.health) {
            renderHealthBadge(data.health);
        }

        // Show payment status
        if (data.payment_status === 'completed') {
            showEstimatePanel();
            showPaymentBadge();
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

        // Render health score
        if (data.health) {
            renderHealthBadge(data.health);
            renderHealthBreakdown(data.health);
        }

        // Render vehicle info
        if (data.vehicle_info && data.vin) {
            renderVehicleBar(data.vehicle_info, data.vin);
        }

        // Render root cause correlations
        if (data.correlations && data.correlations.length > 0) {
            renderCorrelations(data.correlations);
        }

        // Check payment status from snapshot response
        if (data.payment_status === 'completed') {
            showEstimatePanel();
            showPaymentBadge();
        }
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

        // Show estimate panel after diagnosis
        showEstimatePanel();

        // Show report button
        document.getElementById('reportBtn').style.display = '';
    } catch (e) {
        output.textContent = 'Error: Could not reach LLM. Is the server running?';
    }

    btn.disabled = false;
    btn.textContent = 'Analyze';
    isAnalyzing = false;
}

// ─── Vehicle Info ───

function renderVehicleBar(info, vin) {
    const bar = document.getElementById('vehicleBar');
    const nameEl = document.getElementById('vehicleName');
    const vinEl = document.getElementById('vehicleVin');

    // Build display string
    let parts = [];
    if (info.year) parts.push(info.year);
    if (info.make) parts.push(info.make);
    if (info.model) parts.push(info.model);
    if (info.displacement_l) parts.push(info.displacement_l + 'L');
    nameEl.textContent = parts.join(' ') || 'Unknown Vehicle';
    vinEl.textContent = vin;
    bar.style.display = '';
}

// ─── Health Score ───

function renderHealthBadge(health) {
    const badge = document.getElementById('healthBadge');
    const scoreEl = document.getElementById('healthScore');
    const gradeEl = document.getElementById('healthGrade');

    scoreEl.textContent = health.total;
    gradeEl.textContent = health.grade;

    // Color the badge by grade
    badge.className = 'health-badge grade-' + health.grade.toLowerCase();
    badge.style.display = '';
}

function renderHealthBreakdown(health) {
    if (!health.breakdown) return;

    const panel = document.getElementById('healthPanel');
    const grid = document.getElementById('healthGrid');

    const entries = Object.entries(health.breakdown);
    if (entries.length === 0) return;

    panel.style.display = '';
    grid.innerHTML = entries.map(([name, data]) => {
        const color = scoreColor(data.score);
        const label = name.replace(/_/g, ' ');
        return `<div class="health-cell">
            <div class="health-circle" style="background:${color}">${data.score}</div>
            <div class="health-label">${label}</div>
        </div>`;
    }).join('');
}

function scoreColor(score) {
    if (score >= 90) return '#10B981';
    if (score >= 75) return '#22c55e';
    if (score >= 60) return '#eab308';
    if (score >= 40) return '#f97316';
    return '#ef4444';
}

// ─── Root Cause Correlations ───

function renderCorrelations(correlations) {
    const panel = document.getElementById('rootCausePanel');
    const list = document.getElementById('rootCauseList');
    const count = document.getElementById('corrCount');

    if (!correlations || correlations.length === 0) {
        panel.style.display = 'none';
        return;
    }

    panel.style.display = '';
    count.textContent = correlations.length;

    list.innerHTML = correlations.map(corr => {
        const codes = corr.codes.join(' + ');
        const conf = Math.round(corr.confidence * 100);
        return `<div class="corr-item">
            <div class="corr-codes">${codes}</div>
            <div class="corr-cause">${corr.root_cause}</div>
            <div class="corr-fix">${corr.fix}</div>
            <span class="corr-conf">${conf}%</span>
        </div>`;
    }).join('');
}

// ─── Report ───

function viewReport() {
    window.open('/report', '_blank');
}

// ─── Estimate ───

function showEstimatePanel() {
    const panel = document.getElementById('estimatePanel');
    panel.classList.remove('hidden');
    estimateSent = false;
    const btn = document.getElementById('sendEstBtn');
    btn.textContent = 'Send to Customer Screen';
    btn.className = 'btn-send';
    btn.disabled = false;
    updateEstTotal();
}

function updateEstTotal() {
    const diag = parseFloat(document.getElementById('estDiag').value) || 0;
    const parts = parseFloat(document.getElementById('estParts').value) || 0;
    const labor = parseFloat(document.getElementById('estLabor').value) || 0;
    const total = diag + parts + labor;
    document.getElementById('estTotalDisplay').textContent = '$' + total.toFixed(0);
}

async function sendToCustomer() {
    if (estimateSent) return;

    const btn = document.getElementById('sendEstBtn');
    btn.disabled = true;
    btn.textContent = 'Sending...';

    const diag = parseFloat(document.getElementById('estDiag').value) || 0;
    const parts = parseFloat(document.getElementById('estParts').value) || 0;
    const labor = parseFloat(document.getElementById('estLabor').value) || 0;

    try {
        const resp = await fetch('/api/estimate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                diagnosis_fee: diag,
                parts: parts,
                labor: labor,
            }),
        });
        const data = await resp.json();

        if (data.status === 'ok') {
            estimateSent = true;
            btn.textContent = 'Sent to Customer';
            btn.className = 'btn-send sent';
        }
    } catch (e) {
        btn.disabled = false;
        btn.textContent = 'Send to Customer Screen';
    }
}

// ─── Session Management ───

async function newSession() {
    try {
        await fetch('/api/new-session', { method: 'POST' });

        // Reset UI
        document.getElementById('aiOutput').innerHTML =
            '<div class="empty-state">Press Analyze to run diagnostic</div>';
        document.getElementById('aiMeta').textContent = '';
        document.getElementById('estimatePanel').classList.add('hidden');
        document.getElementById('paymentBadge').classList.add('hidden');
        document.getElementById('estDiag').value = '50';
        document.getElementById('estParts').value = '0';
        document.getElementById('estLabor').value = '0';
        document.getElementById('vehicleBar').style.display = 'none';
        document.getElementById('rootCausePanel').style.display = 'none';
        document.getElementById('healthPanel').style.display = 'none';
        document.getElementById('reportBtn').style.display = 'none';
        estimateSent = false;

        checkStatus();
    } catch (e) {
        // Ignore
    }
}

function showPaymentBadge() {
    const badge = document.getElementById('paymentBadge');
    badge.classList.remove('hidden');
}

// ─── Renderers ───

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

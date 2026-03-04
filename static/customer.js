// CWOP-Diag Customer Screen — Frontend Logic

let currentState = "idle";
let pollInterval = null;

// ─── Initialization ───

document.addEventListener("DOMContentLoaded", () => {
    // Check URL params for Stripe redirect return
    const params = new URLSearchParams(window.location.search);
    if (params.get("payment") === "success") {
        verifyPayment(params.get("session_id"));
        return;
    }

    // Start polling customer state
    pollInterval = setInterval(pollState, 2000);
    pollState();
});

// ─── State Polling ───

async function pollState() {
    try {
        const resp = await fetch("/api/customer-state");
        const data = await resp.json();
        updateScreen(data);
    } catch (e) {
        // Server not reachable
    }
}

function updateScreen(data) {
    const newState = mapState(data.status);
    if (newState !== currentState) {
        switchState(newState);
        currentState = newState;
    }

    // Update content based on state
    if (newState === "results") {
        renderResults(data);
    }
    if (newState === "paid") {
        renderPaid(data);
    }
}

function mapState(status) {
    switch (status) {
        case "idle": return "idle";
        case "scanning": return "scanning";
        case "diagnosed": return "results";
        case "estimated": return "results";
        case "paying": return "paying";
        case "paid": return "paid";
        default: return "idle";
    }
}

function switchState(state) {
    // Map state names to element IDs
    const stateMap = {
        idle: "stateIdle",
        scanning: "stateScanning",
        results: "stateResults",
        paying: "statePaying",
        paid: "statePaid",
    };

    document.querySelectorAll(".screen-state").forEach(el => {
        el.classList.remove("active");
    });

    const target = document.getElementById(stateMap[state]);
    if (target) {
        target.classList.add("active");
    }
}

// ─── Results Rendering ───

function renderResults(data) {
    // Vehicle info
    if (data.vehicle_info && data.vin) {
        renderVehicleCard(data.vehicle_info, data.vin, data.health);
    }

    // Issue count
    const count = data.dtc_count || 0;
    const countEl = document.getElementById("issueCount");
    countEl.textContent = count;

    // Color the count badge by max severity
    let maxSeverity = "clear";
    if (data.dtcs) {
        for (const dtc of data.dtcs) {
            if (dtc.severity === "high") { maxSeverity = "high"; break; }
            if (dtc.severity === "moderate") maxSeverity = "moderate";
        }
    }
    countEl.className = "issue-count" + (count === 0 ? " clear" : maxSeverity === "high" ? " high" : "");

    // DTC chips
    const summary = document.getElementById("dtcSummary");
    if (data.dtcs && data.dtcs.length > 0) {
        summary.innerHTML = data.dtcs.map(dtc =>
            `<span class="dtc-chip ${dtc.severity}">${dtc.code}</span>`
        ).join("");
    } else {
        summary.innerHTML = "";
    }

    // Diagnosis text
    if (data.diagnosis) {
        document.getElementById("customerDiagnosis").textContent = data.diagnosis;
    }

    // Estimate card
    const estimateCard = document.getElementById("estimateCard");
    if (data.status === "estimated" || data.status === "paying") {
        estimateCard.classList.remove("hidden");
        const est = data.estimate;
        document.getElementById("estDiagFee").textContent = "$" + est.diagnosis_fee.toFixed(2);
        document.getElementById("estParts").textContent = "$" + est.parts.toFixed(2);
        document.getElementById("estLabor").textContent = "$" + est.labor.toFixed(2);
        document.getElementById("estTotal").textContent = "$" + est.total.toFixed(2);
        document.getElementById("payAmount").textContent = "$" + est.total.toFixed(2);
    } else {
        estimateCard.classList.add("hidden");
    }
}

function renderVehicleCard(info, vin, health) {
    const card = document.getElementById("vehicleCard");
    const nameEl = document.getElementById("cvName");
    const vinEl = document.getElementById("cvVin");

    let parts = [];
    if (info.year) parts.push(info.year);
    if (info.make) parts.push(info.make);
    if (info.model) parts.push(info.model);
    if (info.displacement_l) parts.push(info.displacement_l + "L");

    nameEl.textContent = parts.join(" ") || "Your Vehicle";
    vinEl.textContent = "VIN: " + vin;
    card.style.display = "";

    // Health score
    if (health && health.total > 0) {
        const healthEl = document.getElementById("cvHealth");
        const scoreEl = document.getElementById("cvScore");
        const gradeEl = document.getElementById("cvGrade");

        scoreEl.textContent = health.total;
        gradeEl.textContent = "Grade " + health.grade;

        // Color by grade
        const colors = { A: "#10B981", B: "#22c55e", C: "#eab308", D: "#f97316", F: "#ef4444" };
        scoreEl.style.color = colors[health.grade] || "#10B981";
        healthEl.style.display = "";
    }
}

function renderPaid(data) {
    const amount = data.payment.amount || data.estimate.total || 0;
    document.getElementById("paidAmount").textContent = "$" + amount.toFixed(2);
}

// ─── Payment ───

async function startPayment() {
    const btn = document.getElementById("payBtn");
    btn.disabled = true;
    btn.textContent = "Processing...";

    try {
        const resp = await fetch("/api/checkout", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });
        const data = await resp.json();

        if (data.demo) {
            // Demo mode — payment simulated on server
            switchState("paying");
            currentState = "paying";
            setTimeout(() => {
                switchState("paid");
                currentState = "paid";
                pollState();
            }, 2000);
            return;
        }

        if (data.url) {
            // Real Stripe — redirect to checkout
            window.location.href = data.url;
            return;
        }

        if (data.error) {
            btn.disabled = false;
            btn.textContent = "Pay Now";
            alert("Payment error: " + data.error);
        }
    } catch (e) {
        btn.disabled = false;
        btn.textContent = "Pay Now";
    }
}

async function verifyPayment(sessionId) {
    // Returning from Stripe redirect — verify payment
    switchState("paying");
    currentState = "paying";

    const maxAttempts = 10;
    for (let i = 0; i < maxAttempts; i++) {
        try {
            const url = sessionId
                ? `/api/payment-status?session_id=${sessionId}`
                : "/api/payment-status";
            const resp = await fetch(url);
            const data = await resp.json();

            if (data.status === "completed") {
                switchState("paid");
                currentState = "paid";
                pollState();
                return;
            }
        } catch (e) {
            // retry
        }
        await new Promise(r => setTimeout(r, 1500));
    }

    // Timeout — show paid anyway (Stripe webhook may be slow)
    switchState("paid");
    currentState = "paid";
}

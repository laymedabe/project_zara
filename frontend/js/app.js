/**
 * Project Zara — Main Application
 * ==================================
 * Initializes the dashboard, connects WebSocket, and handles all UI updates.
 */

// ============================================================================
// INITIALIZATION
// ============================================================================
document.addEventListener('DOMContentLoaded', async () => {
    console.log('[ZARA] Dashboard initializing...');

    // Start clock
    updateClock();
    setInterval(updateClock, 1000);

    // Initialize charts
    initCharts();

    // Load initial dashboard data
    await loadDashboardData();

    // Load historical chart data
    await loadHistoricalCharts(24);

    // Connect WebSocket
    zaraWS.on('sensor_data', handleSensorData);
    zaraWS.on('risk_update', handleRiskUpdate);
    zaraWS.on('alert', handleAlert);
    zaraWS.connect();

    console.log('[ZARA] Dashboard ready');
});


// ============================================================================
// LOAD INITIAL DASHBOARD DATA
// ============================================================================
async function loadDashboardData() {
    try {
        const response = await fetch('/api/dashboard');
        const data = await response.json();

        // Set system mode
        const modeEl = document.getElementById('system-mode');
        modeEl.textContent = data.mode === 'simulator' ? 'Simulator' : 'Live LoRa';
        if (data.mode === 'simulator') {
            modeEl.style.background = 'rgba(245, 158, 11, 0.15)';
            modeEl.style.color = '#f59e0b';
        }

        // Update with latest reading
        if (data.latest_reading) {
            updateSensorCards(data.latest_reading);
        }

        // Update with latest assessment
        if (data.latest_assessment) {
            updateRiskDisplay(data.latest_assessment);
        }

        // Load alerts
        if (data.recent_alerts && data.recent_alerts.length > 0) {
            updateAlertsTable(data.recent_alerts);
        }

        // Stats
        if (data.stats) {
            document.getElementById('footer-readings-count').textContent =
                data.stats.sensor_readings_count || 0;
        }

        // Load rainfall summary
        await loadRainfallSummary();

    } catch (err) {
        console.error('[ZARA] Failed to load dashboard data:', err);
        showToast('Failed to connect to server', 'DANGER');
    }
}


// ============================================================================
// WEBSOCKET EVENT HANDLERS
// ============================================================================

/**
 * Handle incoming sensor data from WebSocket.
 */
function handleSensorData(data) {
    updateSensorCards(data);
    updateRainfallChart(new Date().toISOString(), data.rainfall || 0);
    updateSoilChart(
        new Date().toISOString(),
        data.soil_moisture_1 || 0,
        data.soil_moisture_2 || 0,
        data.soil_moisture_3 || 0
    );

    // Update readings count
    const countEl = document.getElementById('footer-readings-count');
    const current = parseInt(countEl.textContent) || 0;
    countEl.textContent = current + 1;
}

/**
 * Handle incoming risk assessment from WebSocket.
 */
function handleRiskUpdate(data) {
    updateRiskDisplay(data);
    updateRiskChart(new Date().toISOString(), data.composite_score);
    loadRainfallSummary();
}

/**
 * Handle incoming alert from WebSocket.
 */
function handleAlert(data) {
    // Show toast
    showToast(data.message, data.risk_level);

    // Show/update alert banner for WARNING and DANGER
    if (data.risk_level === 'WARNING' || data.risk_level === 'DANGER') {
        const banner = document.getElementById('alert-banner');
        const bannerText = document.getElementById('alert-banner-text');
        const bannerIcon = document.getElementById('alert-banner-icon');

        banner.className = `alert-banner ${data.risk_level === 'DANGER' ? 'danger-banner' : 'warning-banner'}`;
        bannerText.textContent = data.message;
        bannerIcon.textContent = data.risk_level === 'DANGER' ? '🚨' : '⚠️';
    }

    // Add to alerts table
    prependAlert(data);
}


// ============================================================================
// UI UPDATE FUNCTIONS
// ============================================================================

/**
 * Update all sensor cards with new reading data.
 */
function updateSensorCards(data) {
    // Soil Moisture
    for (let i = 1; i <= 3; i++) {
        const value = data[`soil_moisture_${i}`];
        const bar = document.getElementById(`soil-bar-${i}`);
        const valueEl = document.getElementById(`soil-value-${i}`);

        if (value !== null && value !== undefined) {
            bar.style.width = `${Math.min(100, value)}%`;
            bar.style.background = getSoilBarGradient(value);
            valueEl.textContent = `${formatNum(value)}%`;
        }
    }

    // Temperature
    const tempEl = document.getElementById('temp-value');
    tempEl.textContent = formatNum(data.temperature);

    // Humidity
    const humidEl = document.getElementById('humidity-value');
    humidEl.textContent = formatNum(data.humidity);

    // Pressure
    const pressEl = document.getElementById('pressure-value');
    pressEl.textContent = formatNum(data.pressure, 0);

    // Tilt
    const tiltXEl = document.getElementById('tilt-x-value');
    const tiltYEl = document.getElementById('tilt-y-value');
    tiltXEl.textContent = `${formatNum(data.tilt_x, 2)}°`;
    tiltYEl.textContent = `${formatNum(data.tilt_y, 2)}°`;

    // Tilt dot visual
    const tiltDot = document.getElementById('tilt-dot');
    if (data.tilt_x !== undefined && data.tilt_y !== undefined) {
        // Map tilt angles to dot position (max ±15° = edge of circle)
        const maxAngle = 15;
        const xPct = 50 + (data.tilt_x / maxAngle) * 40;
        const yPct = 50 + (data.tilt_y / maxAngle) * 40;
        tiltDot.style.left = `${Math.max(10, Math.min(90, xPct))}%`;
        tiltDot.style.top = `${Math.max(10, Math.min(90, yPct))}%`;

        // Color based on magnitude
        const mag = Math.sqrt(data.tilt_x ** 2 + data.tilt_y ** 2);
        if (mag >= 10) {
            tiltDot.style.background = '#ef4444';
            tiltDot.style.boxShadow = '0 0 12px rgba(239,68,68,0.5)';
        } else if (mag >= 5) {
            tiltDot.style.background = '#f97316';
            tiltDot.style.boxShadow = '0 0 10px rgba(249,115,22,0.4)';
        } else if (mag >= 2) {
            tiltDot.style.background = '#f59e0b';
            tiltDot.style.boxShadow = '0 0 8px rgba(245,158,11,0.3)';
        } else {
            tiltDot.style.background = '#10b981';
            tiltDot.style.boxShadow = '0 0 10px rgba(16,185,129,0.3)';
        }
    }

    // Rainfall
    const rainEl = document.getElementById('rainfall-value');
    rainEl.textContent = formatNum(data.rainfall, 2);
}

/**
 * Update the main risk display (gauge, label, breakdown bars).
 */
function updateRiskDisplay(assessment) {
    const level = assessment.risk_level;
    const score = assessment.composite_score;
    const color = getRiskColor(level);
    const glow = getRiskGlow(level);

    // --- Gauge arc ---
    const arc = document.getElementById('gauge-arc');
    const totalArcLength = 251.2;
    const offset = totalArcLength - (score / 100) * totalArcLength;
    arc.style.strokeDashoffset = offset;
    arc.style.stroke = color;

    // --- Score number ---
    const scoreEl = document.getElementById('risk-score');
    scoreEl.textContent = formatNum(score, 0);
    scoreEl.style.color = color;

    // --- Risk label ---
    const labelEl = document.getElementById('risk-level');
    labelEl.textContent = level;
    labelEl.style.color = color;

    // --- Sublabel ---
    document.getElementById('risk-sublabel').textContent = getRiskSublabel(level);

    // --- Hero section glow ---
    const hero = document.getElementById('risk-hero');
    hero.style.boxShadow = `0 0 60px ${glow}, inset 0 0 30px ${glow}`;
    hero.style.borderColor = `${color}33`;

    // --- Breakdown bars ---
    updateBreakdownBar('rainfall', assessment.rainfall_score);
    updateBreakdownBar('soil', assessment.soil_moisture_score);
    updateBreakdownBar('slope', assessment.slope_movement_score);
    updateBreakdownBar('env', assessment.environmental_score);
}

/**
 * Update a single breakdown bar.
 */
function updateBreakdownBar(key, score) {
    const fill = document.getElementById(`breakdown-${key}`);
    const val = document.getElementById(`breakdown-${key}-val`);

    if (fill && val && score !== undefined) {
        fill.style.width = `${Math.min(100, score)}%`;
        fill.style.background = getBreakdownColor(score);
        val.textContent = formatNum(score, 0);
        val.style.color = getBreakdownColor(score);
    }
}

/**
 * Load and display rainfall summary (1hr, 3hr, 24hr, 72hr).
 */
async function loadRainfallSummary() {
    try {
        const response = await fetch('/api/rainfall');
        const data = await response.json();

        const windows = ['1hr', '3hr', '24hr', '72hr'];
        for (const w of windows) {
            const card = document.getElementById(`rain-${w}`);
            if (card) {
                const valueEl = card.querySelector('.rain-value');
                if (valueEl) {
                    valueEl.textContent = formatNum(data[`rainfall_${w}`], 1);
                }
            }
        }
    } catch (err) {
        console.error('[ZARA] Failed to load rainfall summary:', err);
    }
}

/**
 * Update the alerts table with a list of alerts.
 */
function updateAlertsTable(alerts) {
    const tbody = document.getElementById('alerts-tbody');
    tbody.innerHTML = '';

    for (const alert of alerts) {
        const row = createAlertRow(alert);
        tbody.appendChild(row);
    }
}

/**
 * Prepend a new alert to the top of the alerts table.
 */
function prependAlert(alert) {
    const tbody = document.getElementById('alerts-tbody');

    // Remove empty row if present
    const emptyRow = tbody.querySelector('.empty-row');
    if (emptyRow) emptyRow.remove();

    const row = createAlertRow(alert);
    row.style.animation = 'toastIn 0.4s ease';
    tbody.insertBefore(row, tbody.firstChild);

    // Keep table to 50 rows max
    while (tbody.children.length > 50) {
        tbody.removeChild(tbody.lastChild);
    }
}

/**
 * Create a table row element for an alert.
 */
function createAlertRow(alert) {
    const row = document.createElement('tr');
    const statusText = alert.acknowledged
        ? `<span class="alert-status acknowledged">Acknowledged</span>`
        : `<span class="alert-status">Active</span>`;

    row.innerHTML = `
        <td>${formatDateTime(alert.timestamp)}</td>
        <td>${createRiskBadge(alert.risk_level)}</td>
        <td>${formatNum(alert.composite_score, 1) || '--'}</td>
        <td>${alert.message}</td>
        <td>${statusText}</td>
    `;
    return row;
}

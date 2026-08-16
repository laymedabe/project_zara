/**
 * Project Zara — Chart Manager
 * ==============================
 * Manages Chart.js instances for rainfall, soil moisture, and risk history.
 * All charts auto-update via WebSocket data.
 */

// Chart.js global configuration
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.04)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.pointStyleWidth = 8;
Chart.defaults.animation.duration = 600;

// Maximum data points per chart
const MAX_CHART_POINTS = 100;

/**
 * Chart instances (global).
 */
let rainfallChart = null;
let soilChart = null;
let riskChart = null;

/**
 * Initialize all charts.
 */
function initCharts() {
    _initRainfallChart();
    _initSoilChart();
    _initRiskChart();
}

/**
 * Initialize the rainfall time-series chart.
 */
function _initRainfallChart() {
    const ctx = document.getElementById('rainfall-chart').getContext('2d');

    rainfallChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: 'Rainfall (mm)',
                data: [],
                backgroundColor: 'rgba(59, 130, 246, 0.5)',
                borderColor: '#3b82f6',
                borderWidth: 1,
                borderRadius: 3,
                barPercentage: 0.7,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 12, font: { size: 10 } },
                },
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    title: { display: true, text: 'mm', font: { size: 10 } },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 10,
                    cornerRadius: 8,
                },
            },
        },
    });
}

/**
 * Initialize the soil moisture multi-line chart.
 */
function _initSoilChart() {
    const ctx = document.getElementById('soil-chart').getContext('2d');

    soilChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [
                {
                    label: 'Shallow (15cm)',
                    data: [],
                    borderColor: '#10b981',
                    backgroundColor: 'rgba(16, 185, 129, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHitRadius: 10,
                },
                {
                    label: 'Mid (30cm)',
                    data: [],
                    borderColor: '#f59e0b',
                    backgroundColor: 'rgba(245, 158, 11, 0.05)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHitRadius: 10,
                },
                {
                    label: 'Deep (60cm)',
                    data: [],
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.05)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4,
                    pointRadius: 0,
                    pointHitRadius: 10,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 12, font: { size: 10 } },
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    title: { display: true, text: '%', font: { size: 10 } },
                },
            },
            plugins: {
                legend: {
                    position: 'top',
                    labels: { boxWidth: 8, padding: 16, font: { size: 10 } },
                },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 10,
                    cornerRadius: 8,
                },
            },
        },
    });
}

/**
 * Initialize the risk score history chart.
 */
function _initRiskChart() {
    const ctx = document.getElementById('risk-chart').getContext('2d');

    riskChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Risk Score',
                data: [],
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2.5,
                fill: true,
                tension: 0.3,
                pointRadius: 3,
                pointBackgroundColor: '#10b981',
                pointBorderColor: 'transparent',
                pointHitRadius: 10,
                segment: {
                    borderColor: function(ctx) {
                        const val = ctx.p1.parsed.y;
                        if (val >= 91) return '#ef4444';
                        if (val >= 61) return '#f97316';
                        if (val >= 31) return '#f59e0b';
                        return '#10b981';
                    },
                    backgroundColor: function(ctx) {
                        const val = ctx.p1.parsed.y;
                        if (val >= 91) return 'rgba(239, 68, 68, 0.1)';
                        if (val >= 61) return 'rgba(249, 115, 22, 0.1)';
                        if (val >= 31) return 'rgba(245, 158, 11, 0.1)';
                        return 'rgba(16, 185, 129, 0.1)';
                    },
                },
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { intersect: false, mode: 'index' },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 15, font: { size: 10 } },
                },
                y: {
                    min: 0,
                    max: 100,
                    grid: { color: 'rgba(255,255,255,0.03)' },
                    title: { display: true, text: 'Risk %', font: { size: 10 } },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(17, 24, 39, 0.95)',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 10,
                    cornerRadius: 8,
                    callbacks: {
                        label: function(context) {
                            const val = context.parsed.y;
                            let level = 'SAFE';
                            if (val >= 91) level = 'DANGER';
                            else if (val >= 61) level = 'WARNING';
                            else if (val >= 31) level = 'CAUTION';
                            return `Risk: ${val.toFixed(1)}% (${level})`;
                        },
                    },
                },
            },
        },
    });
}

/**
 * Add a new data point to the rainfall chart.
 */
function updateRainfallChart(timestamp, rainfall) {
    if (!rainfallChart) return;
    const label = formatTime(timestamp);

    rainfallChart.data.labels.push(label);
    rainfallChart.data.datasets[0].data.push(rainfall);

    // Trim to max points
    if (rainfallChart.data.labels.length > MAX_CHART_POINTS) {
        rainfallChart.data.labels.shift();
        rainfallChart.data.datasets[0].data.shift();
    }

    rainfallChart.update('none');
}

/**
 * Add a new data point to the soil moisture chart.
 */
function updateSoilChart(timestamp, sm1, sm2, sm3) {
    if (!soilChart) return;
    const label = formatTime(timestamp);

    soilChart.data.labels.push(label);
    soilChart.data.datasets[0].data.push(sm1);
    soilChart.data.datasets[1].data.push(sm2);
    soilChart.data.datasets[2].data.push(sm3);

    if (soilChart.data.labels.length > MAX_CHART_POINTS) {
        soilChart.data.labels.shift();
        soilChart.data.datasets.forEach(ds => ds.data.shift());
    }

    soilChart.update('none');
}

/**
 * Add a new data point to the risk history chart.
 */
function updateRiskChart(timestamp, score) {
    if (!riskChart) return;
    const label = formatTime(timestamp);

    riskChart.data.labels.push(label);
    riskChart.data.datasets[0].data.push(score);

    if (riskChart.data.labels.length > MAX_CHART_POINTS) {
        riskChart.data.labels.shift();
        riskChart.data.datasets[0].data.shift();
    }

    riskChart.update('none');
}

/**
 * Load historical chart data from the API.
 */
async function loadHistoricalCharts(hours = 24) {
    try {
        const [readingsRes, assessmentsRes] = await Promise.all([
            fetch(`/api/readings?hours=${hours}`),
            fetch(`/api/assessments?hours=${hours}`),
        ]);

        const readingsData = await readingsRes.json();
        const assessmentsData = await assessmentsRes.json();

        // Populate charts with historical data (oldest first)
        const readings = (readingsData.readings || []).reverse();
        const assessments = (assessmentsData.assessments || []).reverse();

        // Rainfall & Soil charts
        readings.forEach(r => {
            const label = formatTime(r.timestamp);
            rainfallChart.data.labels.push(label);
            rainfallChart.data.datasets[0].data.push(r.rainfall || 0);
            soilChart.data.labels.push(label);
            soilChart.data.datasets[0].data.push(r.soil_moisture_1 || 0);
            soilChart.data.datasets[1].data.push(r.soil_moisture_2 || 0);
            soilChart.data.datasets[2].data.push(r.soil_moisture_3 || 0);
        });

        // Risk chart
        assessments.forEach(a => {
            riskChart.data.labels.push(formatTime(a.timestamp));
            riskChart.data.datasets[0].data.push(a.composite_score);
        });

        rainfallChart.update('none');
        soilChart.update('none');
        riskChart.update('none');

    } catch (err) {
        console.error('[CHARTS] Failed to load historical data:', err);
    }
}

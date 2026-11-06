/**
 * Project Zara — Utility Functions
 * =================================
 * Helper functions used across the dashboard.
 */

/**
 * Get the CSS color for a risk level.
 */
function getRiskColor(level) {
    const colors = {
        'SAFE': '#10b981',
        'CAUTION': '#f59e0b',
        'WARNING': '#f97316',
        'DANGER': '#ef4444',
    };
    return colors[level] || '#64748b';
}

/**
 * Get the CSS class name for a risk level.
 */
function getRiskClass(level) {
    return (level || '').toLowerCase();
}

/**
 * Get the glow color for a risk level.
 */
function getRiskGlow(level) {
    const glows = {
        'SAFE': 'rgba(16, 185, 129, 0.3)',
        'CAUTION': 'rgba(245, 158, 11, 0.3)',
        'WARNING': 'rgba(249, 115, 22, 0.3)',
        'DANGER': 'rgba(239, 68, 68, 0.3)',
    };
    return glows[level] || 'transparent';
}

/**
 * Get the sublabel text for a risk level.
 */
function getRiskSublabel(level) {
    const labels = {
        'SAFE': 'All conditions within normal range',
        'CAUTION': 'Elevated conditions — monitor closely',
        'WARNING': 'High risk — prepare for evacuation',
        'DANGER': 'Critical risk — EVACUATE IMMEDIATELY',
    };
    return labels[level] || 'Analyzing...';
}

/**
 * Format a timestamp to a human-readable time string.
 */
function formatTime(timestamp) {
    if (!timestamp) return '--:--';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-PH', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
    });
}

/**
 * Format a timestamp to a human-readable date + time string.
 */
function formatDateTime(timestamp) {
    if (!timestamp) return '---';
    const date = new Date(timestamp);
    return date.toLocaleString('en-PH', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: true,
    });
}

/**
 * Format a number to a fixed decimal string. Returns '--' for null/undefined.
 */
function formatNum(value, decimals = 1) {
    if (value === null || value === undefined || isNaN(value)) return '--';
    return Number(value).toFixed(decimals);
}

/**
 * Show a toast notification.
 */
function showToast(message, level = 'safe', durationMs = 6000) {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${getRiskClass(level)}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('fadeout');
        setTimeout(() => toast.remove(), 400);
    }, durationMs);
}

/**
 * Create a risk badge HTML element.
 */
function createRiskBadge(level) {
    return `<span class="risk-badge ${getRiskClass(level)}">${level}</span>`;
}

/**
 * Get the color for a soil moisture bar based on value.
 */
function getSoilBarGradient(value) {
    if (value >= 85) return 'linear-gradient(90deg, #ef4444, #dc2626)';
    if (value >= 70) return 'linear-gradient(90deg, #f97316, #ea580c)';
    if (value >= 55) return 'linear-gradient(90deg, #f59e0b, #d97706)';
    return 'linear-gradient(90deg, #10b981, #059669)';
}

/**
 * Get breakdown bar color based on score.
 */
function getBreakdownColor(score) {
    if (score >= 91) return '#ef4444';
    if (score >= 61) return '#f97316';
    if (score >= 31) return '#f59e0b';
    return '#10b981';
}

/**
 * Update the clock display.
 */
function updateClock() {
    const now = new Date();
    document.getElementById('current-time').textContent =
        now.toLocaleTimeString('en-PH', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true });
    document.getElementById('current-date').textContent =
        now.toLocaleDateString('en-PH', { weekday: 'short', year: 'numeric', month: 'long', day: 'numeric' });
}

/**
 * Export sensor data as CSV.
 */
async function exportCSV() {
    try {
        const response = await fetch('/api/readings?hours=168');
        const data = await response.json();
        const readings = data.readings;

        if (!readings || readings.length === 0) {
            showToast('No data to export', 'CAUTION');
            return;
        }

        const headers = Object.keys(readings[0]).join(',');
        const rows = readings.map(r => Object.values(r).join(','));
        const csv = headers + '\n' + rows.join('\n');

        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `zara_data_${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
        URL.revokeObjectURL(url);

        showToast('CSV exported successfully', 'SAFE');
    } catch (err) {
        showToast('Export failed: ' + err.message, 'DANGER');
    }
}

/**
 * Dismiss the alert banner.
 */
function dismissAlertBanner() {
    document.getElementById('alert-banner').classList.add('hidden');
}

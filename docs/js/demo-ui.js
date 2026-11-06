/**
 * Project Iraya — Demo UI
 * ========================
 * Scenario controls and chart-range selectors for the static showcase.
 */

document.addEventListener('DOMContentLoaded', () => {
    const buttons = document.querySelectorAll('[data-sim-mode]');
    const pauseBtn = document.getElementById('sim-pause');
    const statusEl = document.getElementById('sim-status');

    buttons.forEach(btn => {
        btn.addEventListener('click', () => ZaraDemo.setMode(btn.dataset.simMode));
    });

    pauseBtn.addEventListener('click', () => {
        ZaraDemo.getState().paused ? ZaraDemo.start() : ZaraDemo.stop();
    });

    ZaraDemo.onState(state => {
        buttons.forEach(btn => {
            const active = btn.dataset.simMode === state.mode;
            btn.classList.toggle('active', active);
            btn.setAttribute('aria-pressed', String(active));
        });

        pauseBtn.textContent = state.paused ? '▶ Resume' : '⏸ Pause';

        let text = `Now simulating: <strong>${state.scenarioLabel}</strong>`;
        if (state.paused) {
            text += ' · paused';
        } else if (state.mode === 'auto') {
            text += ` · ${state.nextLabel} in ${Math.max(0, Math.round(state.secondsToNext))}s`;
        }
        statusEl.innerHTML = text;
    });

    // Chart range selectors (1 hr = 12 readings at the 5-minute interval).
    async function reloadSeries(chart, hours, mapRow) {
        const res = await fetch(`/api/readings?hours=${hours}`);
        const rows = (await res.json()).readings.reverse().slice(-MAX_CHART_POINTS);
        chart.data.labels = rows.map(r => formatTime(r.timestamp));
        mapRow(rows);
        chart.update('none');
    }

    document.getElementById('rainfall-chart-range').addEventListener('change', e => {
        reloadSeries(rainfallChart, e.target.value, rows => {
            rainfallChart.data.datasets[0].data = rows.map(r => r.rainfall || 0);
        });
    });

    document.getElementById('soil-chart-range').addEventListener('change', e => {
        reloadSeries(soilChart, e.target.value, rows => {
            soilChart.data.datasets[0].data = rows.map(r => r.soil_moisture_1 || 0);
            soilChart.data.datasets[1].data = rows.map(r => r.soil_moisture_2 || 0);
        });
    });
});

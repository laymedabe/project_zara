/**
 * Project Iraya — In-Browser Demo Backend
 * =========================================
 * Replaces the FastAPI server + SQLite + LoRa receiver so the dashboard can run
 * as a static site (e.g. GitHub Pages). Contains JavaScript ports of:
 *   - backend/lora_simulator.py   (sensor data generation)
 *   - backend/data_processor.py   (feature extraction)
 *   - backend/risk_engine.py      (composite risk scoring)
 *   - backend/alert_manager.py    (alert messages)
 *
 * It exposes the same surface the real dashboard uses:
 *   - `zaraWS` (on / off / connect / disconnect) instead of websocket.js
 *   - `fetch('/api/...')` is intercepted and answered from in-memory data
 *
 * Time compression: each reading represents one 5-minute sensor interval
 * (SENSOR_INTERVAL_SECONDS = 300 on the Raspberry Pi), but readings arrive
 * every TICK_MS in the browser. Rolling windows are therefore counted in
 * readings: 1 hr = 12 readings, 3 hr = 36, 24 hr = 288, 72 hr = 864.
 */

const ZaraDemo = (() => {
    // ── Config (mirrors backend/config.py) ─────────────────────────────────
    const TICK_MS = 2000;
    const READINGS_PER_HOUR = 12;
    const MAX_READINGS = 72 * READINGS_PER_HOUR;

    const RAINFALL_THRESHOLDS = {
        '1hr':  { caution: 10,  warning: 30,  danger: 50 },
        '3hr':  { caution: 15,  warning: 30,  danger: 65 },
        '24hr': { caution: 50,  warning: 100, danger: 200 },
        '72hr': { caution: 100, warning: 200, danger: 350 },
    };
    const WINDOW_HOURS = { '1hr': 1, '3hr': 3, '24hr': 24, '72hr': 72 };
    const SOIL_THRESHOLDS = [
        { caution: 60, warning: 75, danger: 85 },   // Sensor 1 (A0)
        { caution: 55, warning: 70, danger: 82 },   // Sensor 2 (A1)
    ];
    const SOIL_WEIGHTS = [0.55, 0.45];
    const TILT_THRESHOLDS = { caution: 0.10, warning: 0.30, danger: 0.50 };
    const HUMIDITY_THRESHOLD_HIGH = 90;
    const PRESSURE_DROP_THRESHOLD = 3.0;
    const RISK_WEIGHTS = {
        rainfall: 0.35, soil_moisture: 0.30, slope_movement: 0.20, environmental: 0.15,
    };

    // ── Scenarios ──────────────────────────────────────────────────────────
    // Ranges are calibrated so each scenario lands in its intended risk band.
    const SCENARIOS = {
        calm: {
            label: 'Calm', sm1: [28, 38], sm2: [22, 32], tilt: 0.05,
            temp: [27, 31], hum: [58, 68], press: [1010, 1013], rain: [0, 0.08],
        },
        steady: {
            label: 'Steady Rain', sm1: [52, 62], sm2: [48, 58], tilt: 0.2,
            temp: [24, 27], hum: [78, 87], press: [1005, 1008], rain: [0.8, 1.4],
        },
        heavy: {
            label: 'Heavy Rain', sm1: [68, 80], sm2: [62, 72], tilt: 0.45,
            temp: [22, 25], hum: [88, 95], press: [999, 1003], rain: [2.5, 4.5],
        },
        typhoon: {
            label: 'Typhoon', sm1: [84, 95], sm2: [78, 90], tilt: 1.0,
            temp: [20, 23], hum: [94, 99], press: [986, 995], rain: [6, 10],
        },
        clearing: {
            label: 'Clearing', sm1: [40, 50], sm2: [35, 45], tilt: 0.08,
            temp: [25, 29], hum: [70, 80], press: [1006, 1010], rain: [0, 0],
            slowSoil: true,
        },
    };

    // Auto mode timeline: a full storm event, then a fresh day.
    const TIMELINE = [
        { scenario: 'calm',     ticks: 12 },
        { scenario: 'steady',   ticks: 18 },
        { scenario: 'heavy',    ticks: 15 },
        { scenario: 'typhoon',  ticks: 15 },
        { scenario: 'clearing', ticks: 30 },
    ];

    // ── State ──────────────────────────────────────────────────────────────
    const readings = [];      // all readings (newest last), for charts/API
    const assessments = [];
    const alerts = [];
    let windowBuf = [];       // readings considered by the risk engine
    let nextId = 1;
    let packetId = 0;
    let sensor = null;        // smoothed sensor state
    let mode = 'auto';        // 'auto' | scenario key
    let phaseIdx = 0;
    let phaseTick = 6;        // start partway into "calm" so the storm comes soon
    let timer = null;
    let paused = false;
    let lastLevel = null;
    const listeners = {};
    const stateListeners = [];

    // ── Helpers ────────────────────────────────────────────────────────────
    const rand = (lo, hi) => lo + Math.random() * (hi - lo);
    const randIn = ([lo, hi]) => rand(lo, hi);
    const round = (v, d = 1) => Math.round(v * 10 ** d) / 10 ** d;
    const sum = (arr, f) => arr.reduce((s, x) => s + (f(x) || 0), 0);

    function currentScenarioKey() {
        return mode === 'auto' ? TIMELINE[phaseIdx].scenario : mode;
    }

    function orientationFor(tx, ty) {
        const parts = [];
        if (ty > 0.15) parts.push('Tilting Forward');
        else if (ty < -0.15) parts.push('Tilting Backward');
        if (tx > 0.15) parts.push('Tilting Right');
        else if (tx < -0.15) parts.push('Tilting Left');
        return parts.length ? parts.join(' & ') : 'Flat';
    }

    function snapToScenario(key) {
        const s = SCENARIOS[key];
        sensor = {
            soil_moisture_1: randIn(s.sm1), soil_moisture_2: randIn(s.sm2),
            tilt_x: rand(-s.tilt, s.tilt) * 0.5, tilt_y: rand(-s.tilt, s.tilt) * 0.5,
            temperature: randIn(s.temp), humidity: randIn(s.hum), pressure: randIn(s.press),
        };
    }

    // ── lora_simulator.py ──────────────────────────────────────────────────
    function generateReading(timestamp) {
        const s = SCENARIOS[currentScenarioKey()];
        if (!sensor) snapToScenario(currentScenarioKey());

        const ease = (prev, target, k) => prev + (target - prev) * k;
        const soilK = s.slowSoil ? 0.06 : 0.3;
        sensor.soil_moisture_1 = ease(sensor.soil_moisture_1, randIn(s.sm1), soilK);
        sensor.soil_moisture_2 = ease(sensor.soil_moisture_2, randIn(s.sm2), soilK);
        sensor.tilt_x = ease(sensor.tilt_x, rand(-s.tilt, s.tilt), 0.5);
        sensor.tilt_y = ease(sensor.tilt_y, rand(-s.tilt, s.tilt), 0.5);
        sensor.temperature = ease(sensor.temperature, randIn(s.temp), 0.35);
        sensor.humidity = Math.min(100, ease(sensor.humidity, randIn(s.hum), 0.35));
        sensor.pressure = ease(sensor.pressure, randIn(s.press), 0.25);

        packetId += 1;
        return {
            id: nextId++,
            timestamp: new Date(timestamp).toISOString(),
            soil_moisture_1: round(sensor.soil_moisture_1, 2),
            soil_moisture_2: round(sensor.soil_moisture_2, 2),
            soil_moisture_3: null,
            tilt_x: round(sensor.tilt_x, 3),
            tilt_y: round(sensor.tilt_y, 3),
            orientation: orientationFor(sensor.tilt_x, sensor.tilt_y),
            temperature: round(sensor.temperature, 2),
            humidity: round(sensor.humidity, 2),
            pressure: round(sensor.pressure, 2),
            rainfall: round(randIn(s.rain), 2),
            packet_id: packetId,
            rssi: Math.round(rand(-112, -96)),
            snr: round(rand(4, 9.5), 1),
            is_valid: 1,
        };
    }

    // ── data_processor.py ──────────────────────────────────────────────────
    function lastN(n) {
        return windowBuf.slice(-n);
    }

    function rainfallSums(includeCurrent) {
        const out = {};
        for (const w of Object.keys(WINDOW_HOURS)) {
            const n = WINDOW_HOURS[w] * READINGS_PER_HOUR;
            out[`rainfall_${w}`] = round(sum(lastN(n), r => r.rainfall)
                + (includeCurrent ? includeCurrent.rainfall : 0), 2);
        }
        return out;
    }

    function extractFeatures(reading) {
        // The reading is not yet in windowBuf (same as "not in DB yet").
        const f = { ...reading, ...rainfallSums(reading) };
        f.rainfall_intensity = reading.rainfall * 12; // mm/hr for 5-min intervals

        const avg = (r) => ((r.soil_moisture_1 || 0) + (r.soil_moisture_2 || 0)) / 2;
        const pastHour = lastN(READINGS_PER_HOUR);
        const oldest = pastHour[0];
        f.soil_moisture_avg = avg(reading);
        f.soil_moisture_trend = pastHour.length >= 2 ? avg(reading) - avg(oldest) : 0;

        f.tilt_magnitude = Math.hypot(reading.tilt_x, reading.tilt_y);
        f.tilt_rate = pastHour.length >= 2
            ? Math.hypot(reading.tilt_x - oldest.tilt_x, reading.tilt_y - oldest.tilt_y)
            : 0;

        const past3 = lastN(3 * READINGS_PER_HOUR);
        f.pressure_drop_3hr = past3.length >= 2 ? past3[0].pressure - reading.pressure : 0;
        return f;
    }

    // ── risk_engine.py ─────────────────────────────────────────────────────
    function banded(value, t, warnSpan, dangerTop) {
        if (value >= t.danger) return 100;
        if (value >= t.warning) return 61 + (value - t.warning) / (t.danger - t.warning) * dangerTop;
        if (value >= t.caution) return 31 + (value - t.caution) / (t.warning - t.caution) * warnSpan;
        return t.caution > 0 ? (value / t.caution) * 30 : 0;
    }

    function scoreRainfall(f) {
        let max = 0;
        for (const w of Object.keys(RAINFALL_THRESHOLDS)) {
            max = Math.max(max, banded(f[`rainfall_${w}`] || 0, RAINFALL_THRESHOLDS[w], 29, 29));
        }
        if (f.rainfall_intensity > 20) {
            max = Math.min(100, max + Math.min(10, (f.rainfall_intensity - 20) * 0.5));
        }
        return round(max);
    }

    function scoreSoil(f) {
        let score = 0;
        [f.soil_moisture_1, f.soil_moisture_2].forEach((v, i) => {
            score += banded(v || 0, SOIL_THRESHOLDS[i], 30, 39) * SOIL_WEIGHTS[i];
        });
        if (f.soil_moisture_trend > 5) score = Math.min(100, score + Math.min(10, f.soil_moisture_trend));
        return round(score);
    }

    function scoreSlope(f) {
        const mag = banded(f.tilt_magnitude, TILT_THRESHOLDS, 30, 39);
        return round(Math.min(100, mag + Math.min(15, f.tilt_rate * 5)));
    }

    function scoreEnvironmental(f) {
        const h = f.humidity || 0;
        let hs = 0;
        if (h >= 95) hs = 80;
        else if (h >= HUMIDITY_THRESHOLD_HIGH) hs = 40 + (h - HUMIDITY_THRESHOLD_HIGH) / (95 - HUMIDITY_THRESHOLD_HIGH) * 40;
        else if (h >= 70) hs = (h - 70) / (HUMIDITY_THRESHOLD_HIGH - 70) * 40;

        const d = f.pressure_drop_3hr || 0;
        let ps = 0;
        if (d >= PRESSURE_DROP_THRESHOLD * 2) ps = 100;
        else if (d >= PRESSURE_DROP_THRESHOLD) ps = 50 + (d - PRESSURE_DROP_THRESHOLD) / PRESSURE_DROP_THRESHOLD * 50;
        else if (d > 0) ps = d / PRESSURE_DROP_THRESHOLD * 50;

        return round(hs * 0.5 + ps * 0.5);
    }

    function classify(score) {
        if (score >= 91) return 'DANGER';
        if (score >= 61) return 'WARNING';
        if (score >= 31) return 'CAUTION';
        return 'SAFE';
    }

    function assess(f) {
        const rainfall_score = scoreRainfall(f);
        const soil_moisture_score = scoreSoil(f);
        const slope_movement_score = scoreSlope(f);
        const environmental_score = scoreEnvironmental(f);

        let composite =
            rainfall_score * RISK_WEIGHTS.rainfall +
            soil_moisture_score * RISK_WEIGHTS.soil_moisture +
            slope_movement_score * RISK_WEIGHTS.slope_movement +
            environmental_score * RISK_WEIGHTS.environmental;

        // Critical overrides
        if ([rainfall_score, soil_moisture_score, slope_movement_score].some(s => s >= 91)) {
            composite = Math.max(composite, 61);
        }
        if (rainfall_score >= 91 && soil_moisture_score >= 91) composite = Math.max(composite, 91);
        composite = Math.min(100, round(composite));

        return {
            risk_level: classify(composite),
            composite_score: composite,
            rainfall_score, soil_moisture_score, slope_movement_score, environmental_score,
            rainfall_1hr: f.rainfall_1hr, rainfall_3hr: f.rainfall_3hr,
            rainfall_24hr: f.rainfall_24hr, rainfall_72hr: f.rainfall_72hr,
        };
    }

    // ── alert_manager.py ───────────────────────────────────────────────────
    function alertMessage(level, score, a) {
        const s = score.toFixed(1);
        const r24 = (a.rainfall_24hr || 0).toFixed(1);
        switch (level) {
            case 'SAFE': return `Conditions are SAFE. Risk score: ${s}%.`;
            case 'CAUTION': return `CAUTION — Elevated landslide risk detected. Score: ${s}%. Monitor conditions closely.`;
            case 'WARNING': return `⚠️ WARNING — High landslide risk! Score: ${s}%. Prepare for possible evacuation. Rainfall 24hr: ${r24}mm.`;
            default: return `🚨 DANGER — Critical landslide risk! Score: ${s}%. EVACUATE IMMEDIATELY. Rainfall 24hr: ${r24}mm. Soil saturation critical.`;
        }
    }

    // ── Pipeline (main.py on_sensor_data) ──────────────────────────────────
    function process(timestamp, emitEvents) {
        const reading = generateReading(timestamp);
        const features = extractFeatures(reading);
        const assessment = { id: nextId++, timestamp: reading.timestamp, ...assess(features) };

        windowBuf.push(reading);
        readings.push(reading);
        assessments.push(assessment);
        if (windowBuf.length > MAX_READINGS) windowBuf.shift();
        if (readings.length > MAX_READINGS) readings.shift();
        if (assessments.length > MAX_READINGS) assessments.shift();

        if (emitEvents) {
            emit('sensor_data', reading);
            emit('risk_update', assessment);
        }

        // Alert on level transitions (the Pi also drives LEDs + buzzer here).
        if (assessment.risk_level !== lastLevel) {
            const alert = {
                id: nextId++,
                timestamp: reading.timestamp,
                risk_level: assessment.risk_level,
                composite_score: assessment.composite_score,
                message: alertMessage(assessment.risk_level, assessment.composite_score, assessment),
                acknowledged: false,
            };
            alerts.unshift(alert);
            if (alerts.length > 100) alerts.pop();
            if (emitEvents && lastLevel !== null) emit('alert', alert);
            lastLevel = assessment.risk_level;
        }
    }

    function advanceTimeline() {
        if (mode !== 'auto') return;
        phaseTick += 1;
        if (phaseTick >= TIMELINE[phaseIdx].ticks) {
            phaseTick = 0;
            phaseIdx += 1;
            if (phaseIdx >= TIMELINE.length) {
                phaseIdx = 0;
                windowBuf = [];   // a new simulated day: rolling windows reset
                if (typeof showToast === 'function') {
                    showToast('Storm passed — simulation restarting with a new day', 'SAFE', 4000);
                }
            }
        }
    }

    function tick() {
        advanceTimeline();
        process(Date.now(), true);
        notifyState();
    }

    // ── Seed history so charts are populated on first load ─────────────────
    (function seed() {
        const n = 40;
        snapToScenario('calm');
        const start = Date.now() - n * TICK_MS;
        for (let i = 0; i < n; i++) process(start + i * TICK_MS, false);
    })();

    // ── Event bus (zaraWS replacement) ─────────────────────────────────────
    function emit(type, data) {
        (listeners[type] || []).forEach(fn => {
            try { fn(data); } catch (e) { console.error(`[DEMO] Handler error for "${type}":`, e); }
        });
    }

    function setConnectionStatus(text, color) {
        const dot = document.getElementById('connection-dot');
        const label = document.getElementById('connection-status');
        if (!dot || !label) return;
        dot.style.background = color;
        dot.style.boxShadow = `0 0 6px ${color}`;
        label.textContent = text;
        label.style.color = color;
    }

    function start() {
        if (timer) return;
        timer = setInterval(tick, TICK_MS);
        paused = false;
        setConnectionStatus('Receiving (simulated)', '#10b981');
        notifyState();
    }

    function stop() {
        clearInterval(timer);
        timer = null;
        paused = true;
        setConnectionStatus('Paused', '#f59e0b');
        notifyState();
    }

    // ── Public controls for the demo UI ────────────────────────────────────
    function setMode(newMode) {
        if (newMode === 'auto') {
            mode = 'auto';
            phaseIdx = 0;
            phaseTick = 0;
        } else {
            mode = newMode;
        }
        // Jumping straight into a scenario: snap sensors and clear the rolling
        // windows so the risk score reflects the new scenario within seconds.
        windowBuf = [];
        snapToScenario(currentScenarioKey());
        if (paused) start();
        tick();
    }

    function getState() {
        const key = currentScenarioKey();
        const phase = TIMELINE[phaseIdx];
        return {
            mode,
            paused,
            scenario: key,
            scenarioLabel: SCENARIOS[key].label,
            nextLabel: mode === 'auto'
                ? SCENARIOS[TIMELINE[(phaseIdx + 1) % TIMELINE.length].scenario].label
                : null,
            secondsToNext: mode === 'auto' ? (phase.ticks - phaseTick) * TICK_MS / 1000 : null,
        };
    }

    function notifyState() {
        const s = getState();
        stateListeners.forEach(fn => fn(s));
    }

    // ── Fake REST API (fetch interception) ─────────────────────────────────
    function newestFirst(arr, hours) {
        return arr.slice(-hours * READINGS_PER_HOUR).reverse();
    }

    function apiResponse(path, params) {
        switch (path) {
            case '/api/dashboard':
                return {
                    mode: 'simulator',
                    latest_reading: readings[readings.length - 1] || null,
                    latest_assessment: assessments[assessments.length - 1] || null,
                    recent_alerts: alerts.slice(0, 20),
                    stats: { sensor_readings_count: readings.length },
                };
            case '/api/readings':
                return { readings: newestFirst(readings, Number(params.get('hours') || 24)) };
            case '/api/assessments':
                return { assessments: newestFirst(assessments, Number(params.get('hours') || 24)) };
            case '/api/rainfall':
                return rainfallSums(null);
            case '/api/alerts':
                return { alerts: alerts.slice(0, Number(params.get('limit') || 50)) };
            default:
                return null;
        }
    }

    const realFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
        const url = new URL(typeof input === 'string' ? input : input.url, location.href);
        const idx = url.pathname.indexOf('/api/');
        if (idx !== -1) {
            const body = apiResponse(url.pathname.slice(idx), url.searchParams);
            if (body !== null) {
                return Promise.resolve(new Response(JSON.stringify(body), {
                    status: 200, headers: { 'Content-Type': 'application/json' },
                }));
            }
            return Promise.resolve(new Response('{"detail":"Not found"}', { status: 404 }));
        }
        return realFetch(input, init);
    };

    return {
        TICK_MS, SCENARIOS,
        on(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
        off(type, fn) { listeners[type] = (listeners[type] || []).filter(h => h !== fn); },
        start, stop, setMode, getState,
        onState(fn) { stateListeners.push(fn); fn(getState()); },
    };
})();

// Drop-in replacement for websocket.js — app.js calls zaraWS.on/connect.
const zaraWS = {
    on: ZaraDemo.on,
    off: ZaraDemo.off,
    connect: () => setTimeout(ZaraDemo.start, 400),
    disconnect: ZaraDemo.stop,
};

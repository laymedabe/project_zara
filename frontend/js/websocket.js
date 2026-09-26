/**
 * Project Zara — WebSocket Client
 * =================================
 * Manages the WebSocket connection to the backend.
 * Provides automatic reconnection with exponential backoff.
 * Exposes a simple event-based API: zaraWS.on(type, handler) / zaraWS.connect()
 */

const zaraWS = (() => {
    // ── State ──────────────────────────────────────────────────────────────
    let socket = null;
    let reconnectDelay = 2000;       // Start at 2s
    const MAX_DELAY = 30000;         // Cap at 30s
    let reconnectTimer = null;
    let intentionallyClosed = false;

    const handlers = {};             // { type: [fn, fn, ...] }

    // ── DOM helpers ────────────────────────────────────────────────────────
    function setStatus(connected) {
        const dot  = document.getElementById('connection-dot');
        const text = document.getElementById('connection-status');
        if (!dot || !text) return;

        if (connected) {
            dot.style.background  = '#10b981';
            dot.style.boxShadow   = '0 0 6px #10b981';
            text.textContent      = 'Connected';
            text.style.color      = '#10b981';
        } else {
            dot.style.background  = '#ef4444';
            dot.style.boxShadow   = '0 0 6px #ef4444';
            text.textContent      = 'Reconnecting...';
            text.style.color      = '#ef4444';
        }
    }

    // ── Core ───────────────────────────────────────────────────────────────
    function connect() {
        intentionallyClosed = false;

        // Build WebSocket URL from current page host
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${location.host}/ws`;

        console.log(`[WS] Connecting to ${url}`);

        try {
            socket = new WebSocket(url);
        } catch (err) {
            console.error('[WS] Failed to create WebSocket:', err);
            scheduleReconnect();
            return;
        }

        socket.onopen = () => {
            console.log('[WS] Connected');
            reconnectDelay = 2000;   // Reset backoff on success
            setStatus(true);
        };

        socket.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                const type = msg.type;
                const data = msg.data;

                if (handlers[type]) {
                    handlers[type].forEach(fn => {
                        try { fn(data); }
                        catch (e) { console.error(`[WS] Handler error for "${type}":`, e); }
                    });
                }
            } catch (e) {
                console.warn('[WS] Could not parse message:', event.data, e);
            }
        };

        socket.onclose = (event) => {
            console.warn(`[WS] Closed (code=${event.code})`);
            setStatus(false);
            if (!intentionallyClosed) {
                scheduleReconnect();
            }
        };

        socket.onerror = (err) => {
            console.error('[WS] Error:', err);
            // onclose will fire next and trigger reconnect
        };
    }

    function disconnect() {
        intentionallyClosed = true;
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
        if (socket) {
            socket.close();
            socket = null;
        }
    }

    function scheduleReconnect() {
        if (reconnectTimer) return;   // Already scheduled

        console.log(`[WS] Reconnecting in ${reconnectDelay / 1000}s...`);
        reconnectTimer = setTimeout(() => {
            reconnectTimer = null;
            connect();
        }, reconnectDelay);

        // Exponential backoff
        reconnectDelay = Math.min(reconnectDelay * 1.5, MAX_DELAY);
    }

    // ── Public API ─────────────────────────────────────────────────────────
    function on(type, fn) {
        if (!handlers[type]) handlers[type] = [];
        handlers[type].push(fn);
    }

    function off(type, fn) {
        if (!handlers[type]) return;
        handlers[type] = handlers[type].filter(h => h !== fn);
    }

    return { connect, disconnect, on, off };
})();

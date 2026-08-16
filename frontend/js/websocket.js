/**
 * Project Zara — WebSocket Client
 * =================================
 * Handles real-time connection to the backend for live sensor data,
 * risk updates, and alert notifications.
 */

class ZaraWebSocket {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 50;
        this.reconnectDelay = 2000;
        this.handlers = {
            sensor_data: [],
            risk_update: [],
            alert: [],
        };
    }

    /**
     * Connect to the WebSocket server.
     */
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${protocol}//${window.location.host}/ws`;

        console.log(`[WS] Connecting to ${url}...`);
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            console.log('[WS] Connected');
            this.reconnectAttempts = 0;
            this._updateConnectionStatus(true);
        };

        this.ws.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this._dispatch(message.type, message.data);
            } catch (err) {
                console.error('[WS] Failed to parse message:', err);
            }
        };

        this.ws.onclose = (event) => {
            console.log(`[WS] Disconnected (code: ${event.code})`);
            this._updateConnectionStatus(false);
            this._reconnect();
        };

        this.ws.onerror = (error) => {
            console.error('[WS] Error:', error);
        };
    }

    /**
     * Register a handler for a message type.
     */
    on(type, handler) {
        if (this.handlers[type]) {
            this.handlers[type].push(handler);
        }
    }

    /**
     * Dispatch a message to registered handlers.
     */
    _dispatch(type, data) {
        const handlers = this.handlers[type] || [];
        for (const handler of handlers) {
            try {
                handler(data);
            } catch (err) {
                console.error(`[WS] Handler error for ${type}:`, err);
            }
        }
    }

    /**
     * Update the connection status indicator in the header.
     */
    _updateConnectionStatus(connected) {
        const dot = document.getElementById('connection-dot');
        const text = document.getElementById('connection-status');

        if (connected) {
            dot.className = 'status-dot connected';
            text.textContent = 'Live';
        } else {
            dot.className = 'status-dot disconnected';
            text.textContent = 'Reconnecting...';
        }
    }

    /**
     * Auto-reconnect with exponential backoff.
     */
    _reconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('[WS] Max reconnect attempts reached');
            const text = document.getElementById('connection-status');
            text.textContent = 'Disconnected';
            return;
        }

        this.reconnectAttempts++;
        const delay = Math.min(this.reconnectDelay * Math.pow(1.3, this.reconnectAttempts), 30000);

        console.log(`[WS] Reconnecting in ${(delay / 1000).toFixed(1)}s (attempt ${this.reconnectAttempts})...`);

        setTimeout(() => {
            this.connect();
        }, delay);
    }
}

// Global WebSocket instance
const zaraWS = new ZaraWebSocket();

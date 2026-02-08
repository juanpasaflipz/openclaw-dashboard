/**
 * NautilusClient — WebSocket client for Nautilus agent communication.
 * Maps to the Nautilus Gateway WebSocket Protocol.
 */
class NautilusClient {
    constructor() {
        this.ws = null;
        this.sessionId = null;
        this.connected = false;
        this.authenticated = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 3;
        this.messageQueue = [];

        // Event handlers (set by consumer)
        this.onMessage = null;
        this.onThinking = null;
        this.onToolUse = null;
        this.onSessionUpdate = null;
        this.onError = null;
        this.onConnect = null;
        this.onDisconnect = null;
        this.onAuthResult = null;
    }

    connect(wsUrl, authConfig) {
        return new Promise((resolve, reject) => {
            try {
                this.ws = new WebSocket(wsUrl);

                this.ws.onopen = () => {
                    this.connected = true;
                    this.reconnectAttempts = 0;
                    console.log('[Nautilus] Connected to', wsUrl);

                    // Authenticate if needed
                    if (authConfig && authConfig.mode !== 'none') {
                        this.authenticate(authConfig);
                    } else {
                        this.authenticated = true;
                        if (this.onConnect) this.onConnect();
                    }
                    resolve();
                };

                this.ws.onmessage = (event) => {
                    this._handleMessage(event.data);
                };

                this.ws.onerror = (error) => {
                    console.error('[Nautilus] WebSocket error:', error);
                    if (this.onError) this.onError({ type: 'connection', message: 'WebSocket error' });
                    if (!this.connected) reject(error);
                };

                this.ws.onclose = (event) => {
                    const wasConnected = this.connected;
                    this.connected = false;
                    this.authenticated = false;
                    console.log('[Nautilus] Disconnected:', event.code, event.reason);
                    if (this.onDisconnect) this.onDisconnect({ code: event.code, reason: event.reason });

                    if (wasConnected && this.reconnectAttempts < this.maxReconnectAttempts) {
                        this.reconnectAttempts++;
                        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
                        console.log(`[Nautilus] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
                        setTimeout(() => this.connect(wsUrl, authConfig).catch(() => {}), delay);
                    }
                };

            } catch (err) {
                reject(err);
            }
        });
    }

    authenticate(authConfig) {
        const payload = { type: 'auth' };
        if (authConfig.mode === 'pairing') {
            payload.token = authConfig.token;
        } else if (authConfig.mode === 'password') {
            payload.password = authConfig.password;
        }
        this._send(payload);
    }

    sendMessage(sessionId, text) {
        if (!this.connected) {
            console.warn('[Nautilus] Not connected');
            return;
        }
        this._send({
            type: 'message',
            sessionId: sessionId || this.sessionId,
            content: text,
        });
    }

    createSession(metadata) {
        this._send({
            type: 'session.create',
            metadata: metadata || {},
        });
    }

    listSessions() {
        this._send({ type: 'session.list' });
    }

    getHistory(sessionId) {
        this._send({
            type: 'session.history',
            sessionId: sessionId || this.sessionId,
        });
    }

    approveToolUse(requestId) {
        this._send({
            type: 'tool.approve',
            requestId: requestId,
        });
    }

    denyToolUse(requestId) {
        this._send({
            type: 'tool.deny',
            requestId: requestId,
        });
    }

    disconnect() {
        this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect
        if (this.ws) {
            this.ws.close(1000, 'User disconnect');
            this.ws = null;
        }
        this.connected = false;
        this.authenticated = false;
        this.sessionId = null;
    }

    _send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            this.messageQueue.push(data);
        }
    }

    _handleMessage(rawData) {
        let data;
        try {
            data = JSON.parse(rawData);
        } catch {
            console.warn('[Nautilus] Non-JSON message:', rawData);
            return;
        }

        const msgType = data.type || '';

        switch (msgType) {
            case 'auth.ok':
                this.authenticated = true;
                console.log('[Nautilus] Authenticated');
                if (this.onAuthResult) this.onAuthResult({ success: true });
                if (this.onConnect) this.onConnect();
                // Flush queued messages
                while (this.messageQueue.length > 0) {
                    this._send(this.messageQueue.shift());
                }
                break;

            case 'auth.error':
                this.authenticated = false;
                console.error('[Nautilus] Auth failed:', data.message);
                if (this.onAuthResult) this.onAuthResult({ success: false, message: data.message });
                if (this.onError) this.onError({ type: 'auth', message: data.message || 'Authentication failed' });
                break;

            case 'session.created':
                this.sessionId = data.sessionId;
                if (this.onSessionUpdate) this.onSessionUpdate({ type: 'created', sessionId: data.sessionId, metadata: data.metadata });
                break;

            case 'session.list':
                if (this.onSessionUpdate) this.onSessionUpdate({ type: 'list', sessions: data.sessions || [] });
                break;

            case 'session.history':
                if (this.onSessionUpdate) this.onSessionUpdate({ type: 'history', messages: data.messages || [] });
                break;

            case 'thinking':
                if (this.onThinking) this.onThinking({ content: data.content, sessionId: data.sessionId });
                break;

            case 'tool_use':
            case 'tool.request':
                if (this.onToolUse) this.onToolUse({
                    requestId: data.requestId,
                    tool: data.tool || data.name,
                    input: data.input || data.params,
                    output: data.output || data.result,
                    status: data.status || 'pending', // pending, running, completed
                    needsApproval: data.needsApproval || false,
                });
                break;

            case 'tool.result':
                if (this.onToolUse) this.onToolUse({
                    requestId: data.requestId,
                    tool: data.tool || data.name,
                    output: data.output || data.result,
                    status: 'completed',
                });
                break;

            case 'message':
            case 'response':
                if (this.onMessage) this.onMessage({
                    role: 'assistant',
                    content: data.content || data.text || '',
                    sessionId: data.sessionId,
                    metadata: data.metadata || {},
                });
                break;

            case 'error':
                if (this.onError) this.onError({ type: 'runtime', message: data.message || data.error || 'Unknown error' });
                break;

            default:
                console.log('[Nautilus] Unhandled message type:', msgType, data);
                // Pass through as generic message
                if (this.onMessage) this.onMessage({
                    role: 'system',
                    content: JSON.stringify(data),
                    metadata: { raw_type: msgType },
                });
        }
    }
}

// Export for use in dashboard-main.js
window.NautilusClient = NautilusClient;

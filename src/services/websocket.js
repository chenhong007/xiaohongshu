/**
 * WebSocket Service - Real-time sync progress updates
 * Uses Socket.IO client to connect to Flask-SocketIO backend
 */
import { io } from 'socket.io-client';

// Determine WebSocket URL based on current location
const getSocketUrl = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const host = window.location.hostname;
  // Use same port as API or default to 8000
  const port = import.meta.env.VITE_API_PORT || '8000';
  return `${protocol}//${host}:${port}`;
};

class SyncWebSocket {
  constructor() {
    this.socket = null;
    this.connected = false;
    this.listeners = new Map();
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
  }

  /**
   * Connect to WebSocket server
   * @returns {Promise<boolean>} Connection success
   */
  connect() {
    return new Promise((resolve) => {
      if (this.socket?.connected) {
        resolve(true);
        return;
      }

      try {
        const url = getSocketUrl();
        console.log('[WebSocket] Connecting to:', url);

        this.socket = io(url, {
          transports: ['websocket', 'polling'],
          reconnection: true,
          reconnectionAttempts: this.maxReconnectAttempts,
          reconnectionDelay: 1000,
          reconnectionDelayMax: 5000,
          timeout: 10000,
        });

        this.socket.on('connect', () => {
          console.log('[WebSocket] Connected');
          this.connected = true;
          this.reconnectAttempts = 0;
          resolve(true);
        });

        this.socket.on('disconnect', (reason) => {
          console.log('[WebSocket] Disconnected:', reason);
          this.connected = false;
        });

        this.socket.on('connect_error', (error) => {
          console.warn('[WebSocket] Connection error:', error.message);
          this.reconnectAttempts++;
          if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('[WebSocket] Max reconnect attempts reached, falling back to polling');
            resolve(false);
          }
        });

        this.socket.on('connected', (data) => {
          console.log('[WebSocket] Server confirmed connection:', data);
        });

        // Setup event handlers
        this.socket.on('sync_progress', (data) => {
          this._emit('progress', data);
        });

        this.socket.on('sync_log', (data) => {
          this._emit('log', data);
        });

        this.socket.on('sync_completed', (data) => {
          this._emit('completed', data);
        });

        // Timeout fallback
        setTimeout(() => {
          if (!this.connected) {
            console.log('[WebSocket] Connection timeout, falling back to polling');
            resolve(false);
          }
        }, 5000);

      } catch (error) {
        console.warn('[WebSocket] Failed to initialize:', error);
        resolve(false);
      }
    });
  }

  /**
   * Disconnect from WebSocket server
   */
  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
      this.connected = false;
    }
  }

  /**
   * Subscribe to sync updates for all accounts
   */
  subscribeAll() {
    if (!this.socket?.connected) {
      console.warn('[WebSocket] Not connected, cannot subscribe');
      return;
    }
    this.socket.emit('subscribe_sync', { all: true });
  }

  /**
   * Subscribe to sync updates for specific accounts
   * @param {number[]} accountIds - Account IDs to subscribe to
   */
  subscribeAccounts(accountIds) {
    if (!this.socket?.connected) {
      console.warn('[WebSocket] Not connected, cannot subscribe');
      return;
    }
    this.socket.emit('subscribe_sync', { account_ids: accountIds });
  }

  /**
   * Unsubscribe from all sync updates
   */
  unsubscribeAll() {
    if (!this.socket?.connected) return;
    this.socket.emit('unsubscribe_sync', { all: true });
  }

  /**
   * Add event listener
   * @param {string} event - Event type: 'progress', 'log', 'completed'
   * @param {Function} callback - Callback function
   * @returns {Function} Unsubscribe function
   */
  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event).add(callback);
    
    // Return unsubscribe function
    return () => {
      this.listeners.get(event)?.delete(callback);
    };
  }

  /**
   * Remove event listener
   * @param {string} event - Event type
   * @param {Function} callback - Callback function
   */
  off(event, callback) {
    this.listeners.get(event)?.delete(callback);
  }

  /**
   * Emit event to listeners
   * @private
   */
  _emit(event, data) {
    const callbacks = this.listeners.get(event);
    if (callbacks) {
      callbacks.forEach(cb => {
        try {
          cb(data);
        } catch (error) {
          console.error('[WebSocket] Listener error:', error);
        }
      });
    }
  }

  /**
   * Check if WebSocket is connected
   * @returns {boolean}
   */
  isConnected() {
    return this.connected && this.socket?.connected;
  }
}

// Singleton instance
const syncWebSocket = new SyncWebSocket();

export default syncWebSocket;
export { SyncWebSocket };

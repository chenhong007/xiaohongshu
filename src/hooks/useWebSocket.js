import { useState, useEffect, useRef, useCallback } from 'react';
import syncWebSocket from '../services/websocket';

/**
 * Custom hook for WebSocket connection management
 * 
 * Handles:
 * - WebSocket connection lifecycle
 * - Event subscriptions
 * - Automatic reconnection
 * - Fallback to polling when WebSocket unavailable
 * 
 * @param {Object} options
 * @param {Function} options.onProgress - Callback for progress updates
 * @param {Function} options.onCompleted - Callback for sync completion
 * @param {Function} options.onLog - Callback for log messages
 * @param {Function} options.fetchAccounts - Function to fetch accounts (for completion refresh)
 * @param {Function} options.setAccounts - Function to update accounts state
 * @returns {Object} { wsConnected }
 */
export const useWebSocket = ({
  onProgress,
  onCompleted,
  onLog,
  fetchAccounts,
  setAccounts
}) => {
  const [wsConnected, setWsConnected] = useState(false);
  const wsInitializedRef = useRef(false);

  // Initialize WebSocket connection
  useEffect(() => {
    if (wsInitializedRef.current) return;
    wsInitializedRef.current = true;

    const initWebSocket = async () => {
      const connected = await syncWebSocket.connect();
      setWsConnected(connected);
      
      if (connected) {
        console.log('[WebSocket] Connected, subscribing to sync updates');
        syncWebSocket.subscribeAll();
      } else {
        console.log('[WebSocket] Not available, will use polling fallback');
      }
    };

    initWebSocket();

    return () => {
      syncWebSocket.disconnect();
    };
  }, []);

  // WebSocket event listeners
  useEffect(() => {
    if (!wsConnected) return;

    // Handle progress updates
    const unsubProgress = syncWebSocket.on('progress', (data) => {
      console.log('[WebSocket] Progress update:', data);
      
      if (onProgress) {
        onProgress(data);
      }
      
      if (setAccounts) {
        setAccounts(prev => prev.map(acc => {
          if (acc.id === data.account_id) {
            return {
              ...acc,
              status: data.status,
              progress: data.progress,
              loaded_msgs: data.loaded_msgs,
              total_msgs: data.total_msgs,
            };
          }
          return acc;
        }));
      }
    });

    // Handle sync completion
    const unsubCompleted = syncWebSocket.on('completed', (data) => {
      console.log('[WebSocket] Sync completed:', data);
      
      if (onCompleted) {
        onCompleted(data);
      }
      
      // Fetch full account data including sync_logs
      if (fetchAccounts) {
        setTimeout(() => fetchAccounts(true), 500);
      }
    });

    // Handle log messages
    const unsubLog = syncWebSocket.on('log', (data) => {
      if (data.level === 'error' || data.level === 'warn') {
        console.log(`[WebSocket] Sync log [${data.level}]:`, data.message);
      }
      
      if (onLog) {
        onLog(data);
      }
    });

    return () => {
      unsubProgress();
      unsubCompleted();
      unsubLog();
    };
  }, [wsConnected, fetchAccounts, setAccounts, onProgress, onCompleted, onLog]);

  return { wsConnected };
};

export default useWebSocket;

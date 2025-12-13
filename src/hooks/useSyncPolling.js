import { useEffect, useCallback } from 'react';
import { accountApi } from '../services';

/**
 * Custom hook for sync status polling
 * 
 * Provides fallback polling when WebSocket is not available.
 * Uses lightweight status API to reduce data transfer.
 * 
 * @param {Object} options
 * @param {Array} options.accounts - Current accounts list
 * @param {Function} options.setAccounts - Function to update accounts state
 * @param {Function} options.fetchAccounts - Function to fetch full accounts data
 * @param {boolean} options.wsConnected - Whether WebSocket is connected
 * @param {number} options.pollInterval - Polling interval in ms (default: 4000)
 */
export const useSyncPolling = ({
  accounts,
  setAccounts,
  fetchAccounts,
  wsConnected,
  pollInterval = 4000
}) => {
  
  useEffect(() => {
    // Skip polling if WebSocket is connected
    if (wsConnected) return;

    const processingAccounts = accounts.filter(
      acc => acc.status === 'processing' || acc.status === 'pending'
    );
    const isProcessing = processingAccounts.length > 0;
    
    if (!isProcessing) return;

    // Log processing status
    const summary = processingAccounts.map(acc => 
      `${acc.name || acc.user_id}: ${acc.progress || 0}% (${acc.loaded_msgs || 0}/${acc.total_msgs || 0})`
    ).join(', ');
    console.log(`[Polling] Processing ${processingAccounts.length} accounts:`, summary);
    
    // Use lightweight status API
    const timer = setInterval(async () => {
      try {
        const statusList = await accountApi.getStatus();
        
        // Check for completion
        const statusMap = new Map(statusList.map(s => [s.id, s]));
        const justCompleted = accounts.some(acc => {
          const newStatus = statusMap.get(acc.id);
          return newStatus && 
            (acc.status === 'processing' || acc.status === 'pending') &&
            (newStatus.status === 'completed' || newStatus.status === 'failed');
        });
        
        // Merge status into accounts
        setAccounts(prev => prev.map(acc => {
          const newStatus = statusMap.get(acc.id);
          if (newStatus) {
            return {
              ...acc,
              status: newStatus.status,
              progress: newStatus.progress,
              loaded_msgs: newStatus.loaded_msgs,
              total_msgs: newStatus.total_msgs,
              error_message: newStatus.error_message,
              last_sync: newStatus.last_sync,
            };
          }
          return acc;
        }));
        
        // Fetch full data on completion
        if (justCompleted) {
          console.log('[Polling] Sync completed, fetching full data');
          setTimeout(() => fetchAccounts(true), 500);
        }
      } catch (err) {
        console.error('[Polling] Status fetch failed:', err);
      }
    }, pollInterval);
    
    return () => {
      console.log('[Polling] Stopped');
      clearInterval(timer);
    };
  }, [accounts, fetchAccounts, setAccounts, wsConnected, pollInterval]);
};

export default useSyncPolling;

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { AlertCircle } from 'lucide-react';
import { accountApi, authApi, COOKIE_INVALID_EVENT } from '../services';
import { useWebSocket, useSyncPolling } from '../hooks';
import { SyncLogModal } from './SyncLogModal';
import { ActionBar } from './ActionBar';
import { AccountTable } from './AccountTable';

/**
 * Log sync details to console for debugging
 */
const logSyncDetailsToConsole = (account) => {
  if (!account?.sync_logs) return;
  
  const logs = account.sync_logs;
  const summary = logs.summary || {};
  const issues = logs.issues || [];
  
  console.group(
    `%c📋 Sync Log - ${account.name || account.user_id}`,
    'color: #3B82F6; font-weight: bold; font-size: 14px;'
  );
  
  console.log('%c📊 Summary', 'color: #10B981; font-weight: bold;', {
    total: summary.total || 0,
    success: summary.success || 0,
    skipped: summary.skipped || 0,
    rate_limited: summary.rate_limited || 0,
    missing_field: summary.missing_field || 0,
    fetch_failed: summary.fetch_failed || 0,
  });
  
  if (issues.length > 0) {
    console.log('%c⚠️ Issues', 'color: #F59E0B; font-weight: bold;', issues.slice(0, 10));
    if (issues.length > 10) {
      console.log(`... and ${issues.length - 10} more issues`);
    }
  }
  
  console.groupEnd();
};

/**
 * Content Area Component
 * 
 * Main content area for account management featuring:
 * - Account table with selection
 * - Sync controls (fast/deep)
 * - Import/Export functionality
 * - Real-time sync status via WebSocket or polling
 */
export const ContentArea = ({ 
  searchTerm, 
  onAddClick, 
  refreshTrigger, 
  onRefresh,
  accounts,
  setAccounts,
  loading,
  setLoading,
  error,
  setError,
  fetchAccounts,
}) => {
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [logModalOpen, setLogModalOpen] = useState(false);
  const [selectedAccountForLog, setSelectedAccountForLog] = useState(null);
  const [isStopping, setIsStopping] = useState(false);
  
  // Track previous account states for change detection
  const prevAccountsRef = useRef([]);
  const loggedSyncRef = useRef(new Map());

  // Filter accounts by search term
  const filteredAccounts = accounts.filter(acc => 
    acc.name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // WebSocket hook
  const { wsConnected } = useWebSocket({
    fetchAccounts,
    setAccounts
  });

  // Polling fallback hook
  useSyncPolling({
    accounts,
    setAccounts,
    fetchAccounts,
    wsConnected
  });

  // Detect sync completion and log to console
  useEffect(() => {
    accounts.forEach(acc => {
      if (!acc.sync_logs) return;
      
      const prevAcc = prevAccountsRef.current.find(p => p.id === acc.id);
      const statusChanged = prevAcc && 
        (prevAcc.status === 'processing' || prevAcc.status === 'pending') &&
        (acc.status === 'completed' || acc.status === 'failed');
      
      const logEndTime = acc.sync_logs.end_time;
      const lastLoggedTime = loggedSyncRef.current.get(acc.id);
      const hasNewLog = logEndTime && logEndTime !== lastLoggedTime;
      
      if ((statusChanged || hasNewLog) && logEndTime) {
        logSyncDetailsToConsole(acc);
        loggedSyncRef.current.set(acc.id, logEndTime);
      }
    });
    
    prevAccountsRef.current = accounts;
  }, [accounts]);

  // Detect auth errors
  useEffect(() => {
    const hasNewAuthError = accounts.some(acc => {
      const prevAcc = prevAccountsRef.current.find(p => p.id === acc.id);
      if (acc.status === 'failed' && (!prevAcc || prevAcc.status !== 'failed' || prevAcc.error_message !== acc.error_message)) {
        const msg = (acc.error_message || '').toLowerCase();
        return msg.includes('cookie') || msg.includes('login') || msg.includes('expired');
      }
      return false;
    });

    if (hasNewAuthError) {
      console.log('Auth error detected, verifying cookie...');
      authApi.getCurrentUser(true).then(me => {
        if (!me?.is_connected) {
          window.dispatchEvent(new CustomEvent(COOKIE_INVALID_EVENT));
        }
      }).catch(() => {
        window.dispatchEvent(new CustomEvent(COOKIE_INVALID_EVENT));
      });
    }
  }, [accounts]);

  // Selection handlers
  const toggleSelect = useCallback((id) => {
    setSelectedIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    if (selectedIds.size === filteredAccounts.length && filteredAccounts.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredAccounts.map(acc => acc.id)));
    }
  }, [selectedIds.size, filteredAccounts]);

  // Update local account status (optimistic update)
  const updateLocalAccountsStatus = useCallback((ids, status, progress = 0) => {
    const idSet = new Set(ids);
    setAccounts(prev => prev.map(acc => {
      if (idSet.has(acc.id)) {
        return { 
          ...acc, 
          status, 
          progress,
          ...(status === 'processing' ? { loaded_msgs: 0 } : {})
        };
      }
      return acc;
    }));
  }, [setAccounts]);

  // Sync single account
  const handleSync = useCallback(async (accountId, mode = 'fast') => {
    updateLocalAccountsStatus([accountId], 'processing', 0);
    try {
      await accountApi.sync(accountId, mode);
      setTimeout(fetchAccounts, 200);
    } catch (err) {
      console.error('Sync failed:', err);
      setError('Sync failed');
      fetchAccounts();
    }
  }, [updateLocalAccountsStatus, fetchAccounts, setError]);

  // Batch sync
  const handleBatchSync = useCallback(async (mode = 'fast') => {
    const idsToSync = selectedIds.size > 0 ? Array.from(selectedIds) : [];
    
    if (idsToSync.length === 0) {
      if (!confirm('No accounts selected. Sync all accounts?')) return;
        return handleSyncAll(mode);
    }
    
    updateLocalAccountsStatus(idsToSync, 'processing', 0);
    setLoading(true);
    
    try {
      await accountApi.batchSync(idsToSync, mode);
      setSelectedIds(new Set());
      setTimeout(fetchAccounts, 500);
    } catch (err) {
      console.error('Batch sync failed:', err);
      setError('Batch sync failed');
      fetchAccounts();
    } finally {
      setLoading(false);
    }
  }, [selectedIds, updateLocalAccountsStatus, setLoading, fetchAccounts, setError]);

  // Sync all
  const handleSyncAll = useCallback(async (mode = 'fast') => {
    const allIds = accounts.map(acc => acc.id);
    updateLocalAccountsStatus(allIds, 'processing', 0);
    setLoading(true);
    
    try {
      await accountApi.syncAll(mode);
      setTimeout(fetchAccounts, 500);
    } catch (err) {
      console.error('Sync all failed:', err);
      setError('Sync failed');
      fetchAccounts();
    } finally {
      setLoading(false);
    }
  }, [accounts, updateLocalAccountsStatus, setLoading, fetchAccounts, setError]);

  // Stop sync
  const handleStopSync = useCallback(async () => {
    if (!confirm('确定要停止当前同步任务吗？')) return;
    
    setIsStopping(true);
    try {
      const result = await accountApi.stopSync();
      // Update local state immediately to show stopped status
      const stoppedCount = accounts.filter(acc => 
        acc.status === 'processing' || acc.status === 'pending'
      ).length;
      
      setAccounts(prev => prev.map(acc => {
        if (acc.status === 'processing' || acc.status === 'pending') {
          return { ...acc, status: 'failed', progress: 0, error_message: '用户手动停止同步' };
        }
        return acc;
      }));
      
      // Show success message
      if (stoppedCount > 0) {
        console.log(`✅ 已停止 ${stoppedCount} 个同步任务`);
      }
      
      // Refresh to get final state from server
      setTimeout(fetchAccounts, 500);
    } catch (err) {
      console.error('Stop sync failed:', err);
      setError('停止同步失败，请重试');
    } finally {
      setIsStopping(false);
    }
  }, [accounts, fetchAccounts, setError, setAccounts]);

  // Fix missing data
  const handleFixMissing = useCallback(async (accountId) => {
    updateLocalAccountsStatus([accountId], 'processing', 0);
    try {
      const result = await accountApi.fixMissing(accountId, false);
      if (result.missing_count === 0) {
        alert('All notes already have complete data');
        fetchAccounts();
        return;
      }
      setTimeout(fetchAccounts, 200);
    } catch (err) {
      setError('Failed to fix missing data');
      fetchAccounts();
    }
  }, [updateLocalAccountsStatus, fetchAccounts, setError]);

  // Delete accounts
  const handleDelete = useCallback(async () => {
    if (selectedIds.size === 0) {
      alert('Please select accounts to delete');
      return;
    }
    if (!confirm(`Delete ${selectedIds.size} selected accounts?`)) return;
    
    try {
      await accountApi.batchDelete(Array.from(selectedIds));
      setSelectedIds(new Set());
      fetchAccounts();
    } catch (err) {
      setError('Delete failed');
    }
  }, [selectedIds, fetchAccounts, setError]);

  // Reset database
  const handleReset = useCallback(async () => {
    if (!confirm('Clear all data? This cannot be undone.')) return;
    try {
      await accountApi.reset();
      fetchAccounts();
      setSelectedIds(new Set());
    } catch (err) {
      setError('Failed to clear database');
    }
  }, [fetchAccounts, setError]);

  // Import
  const handleImport = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json,.csv,.txt';
    input.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      
      try {
        const text = await file.text();
        let userIds = [];
        
        if (file.name.endsWith('.json')) {
          const data = JSON.parse(text);
          userIds = Array.isArray(data) ? data.map(item => item.user_id || item.id || item) : [];
        } else {
          userIds = text.split('\n').map(line => line.trim()).filter(Boolean);
        }
        
        if (userIds.length === 0) {
          alert('No valid user IDs found');
          return;
        }
        
        let added = 0;
        for (const userId of userIds) {
          try {
            await accountApi.add({ user_id: userId });
            added++;
          } catch (err) {
            if (err.status !== 409) console.error(`Failed to add ${userId}:`, err);
          }
        }
        
        alert(`Imported ${added} accounts`);
        fetchAccounts();
      } catch (err) {
        alert('Import failed: ' + err.message);
      }
    };
    input.click();
  }, [fetchAccounts]);

  // Export
  const handleExport = useCallback(() => {
    const exportData = selectedIds.size > 0 
      ? accounts.filter(acc => selectedIds.has(acc.id))
      : accounts;
    
    if (exportData.length === 0) {
      alert('No data to export');
      return;
    }
    
    const json = JSON.stringify(exportData, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `accounts_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }, [selectedIds, accounts]);

  // Show log modal
  const handleShowLog = useCallback((account) => {
    setSelectedAccountForLog(account);
    setLogModalOpen(true);
  }, []);

  const isProcessing = accounts.some(acc => acc.status === 'processing' || acc.status === 'pending');

  return (
    <div className="flex-1 bg-gray-50 p-6 overflow-auto">
      {/* Error Banner */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700">
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">×</button>
        </div>
      )}
      
      <div className="bg-white rounded-lg shadow-sm border">
        {/* Action Bar */}
        <ActionBar
          onAddClick={onAddClick}
          onImport={handleImport}
          onExport={handleExport}
          onDelete={handleDelete}
          onBatchSync={handleBatchSync}
          onStopSync={handleStopSync}
          onReset={handleReset}
          selectedCount={selectedIds.size}
          isProcessing={isProcessing}
          isStopping={isStopping}
          loading={loading}
          wsConnected={wsConnected}
        />

        {/* Account Table */}
        <AccountTable
          accounts={filteredAccounts}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
          onToggleSelectAll={toggleSelectAll}
          onSync={handleSync}
          onFixMissing={handleFixMissing}
          onShowLog={handleShowLog}
          loading={loading}
        />
      </div>
      
      {/* Sync Log Modal */}
      <SyncLogModal 
        isOpen={logModalOpen} 
        onClose={() => { setLogModalOpen(false); setSelectedAccountForLog(null); }} 
        account={selectedAccountForLog} 
      />
    </div>
  );
};

export default ContentArea;

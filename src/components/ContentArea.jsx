import React, { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, CheckCircle, Circle, Trash2, Upload, Download, AlertCircle, Zap, Database, StopCircle, Wrench } from 'lucide-react';
import { accountApi, authApi, COOKIE_INVALID_EVENT } from '../services';

export const ContentArea = ({ 
  activeTab, 
  searchTerm, 
  onAddClick, 
  refreshTrigger, 
  onRefresh,
  // 从 App 层级传入的缓存状态
  accounts,
  setAccounts,
  loading,
  setLoading,
  error,
  setError,
  fetchAccounts,
}) => {
  const [selectedIds, setSelectedIds] = useState(new Set());
  
  // 记录上一次的账号状态，用于检测变化
  const prevAccountsRef = useRef([]);

  // 过滤账号
  const filteredAccounts = accounts.filter(acc => 
    acc.name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // 触发 Cookie 失效事件
  const emitCookieInvalid = () => {
    window.dispatchEvent(new CustomEvent(COOKIE_INVALID_EVENT));
  };

  // 强制验证 Cookie 状态后再决定是否触发失效事件，避免旧错误反复告警
  const emitCookieInvalidSafely = useCallback(async () => {
    try {
      const me = await authApi.getCurrentUser(true);
      if (!me?.is_connected) {
        emitCookieInvalid();
      }
    } catch (err) {
      console.warn('Force check cookie failed, emit invalid event anyway:', err);
      emitCookieInvalid();
    }
  }, []);

  // 检测认证错误并触发事件
  useEffect(() => {
    // 检查是否有新的失败状态且包含 Cookie 错误
    const hasNewAuthError = accounts.some(acc => {
      // 找到对应的旧状态
      const prevAcc = prevAccountsRef.current.find(p => p.id === acc.id);
      
      // 只有当状态从非 failed 变为 failed，或者 error_message 发生变化时才检查
      if (acc.status === 'failed' && (!prevAcc || prevAcc.status !== 'failed' || prevAcc.error_message !== acc.error_message)) {
        const msg = (acc.error_message || '').toLowerCase();
        return msg.includes('cookie') || msg.includes('登录') || msg.includes('失效') || msg.includes('过期');
      }
      return false;
    });

    if (hasNewAuthError) {
      console.log('Detected auth error in account sync, verifying cookie before emitting invalid event');
      emitCookieInvalidSafely();
    }

    // 更新引用
    prevAccountsRef.current = accounts;
  }, [accounts, emitCookieInvalidSafely]);

  // 轮询更新处理中的账号状态
  useEffect(() => {
    const processingAccounts = accounts.filter(acc => acc.status === 'processing' || acc.status === 'pending');
    const isProcessing = processingAccounts.length > 0;
    
    if (isProcessing) {
      console.log('[同步调试] 检测到正在处理的账号，启动轮询:', processingAccounts.map(acc => ({
        id: acc.id, name: acc.name, status: acc.status, progress: acc.progress
      })));
      const timer = setInterval(() => {
        console.log('[同步调试] 轮询刷新账号列表...');
        fetchAccounts(true);
      }, 2000);
      return () => {
        console.log('[同步调试] 停止轮询');
        clearInterval(timer);
      };
    }
  }, [accounts, fetchAccounts]);

  // 切换选择
  const toggleSelect = (id) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedIds.size === filteredAccounts.length && filteredAccounts.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredAccounts.map(acc => acc.id)));
    }
  };

  // 清空数据库
  const handleReset = async () => {
    if (!confirm('确定要清空所有数据库数据吗？这将无法恢复。')) return;
    
    try {
      await accountApi.reset();
      fetchAccounts();
      setSelectedIds(new Set());
    } catch (err) {
      console.error('Failed to reset db:', err);
      setError('清空数据库失败');
    }
  };

  // 删除选中账号
  const handleDelete = async () => {
    if (selectedIds.size === 0) {
      alert('请先选择要删除的账号');
      return;
    }
    
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 个账号吗？`)) return;
    
    try {
      await accountApi.batchDelete(Array.from(selectedIds));
      setSelectedIds(new Set());
      fetchAccounts();
    } catch (err) {
      console.error('Failed to delete accounts:', err);
      setError('删除账号失败');
    }
  };

  // 更新本地账号状态（乐观更新）
  const updateLocalAccountsStatus = (ids, status, progress = 0) => {
    console.log('[同步调试] 更新账号状态:', { ids, status, progress });
    const idSet = new Set(ids);
    setAccounts(prev => prev.map(acc => {
      if (idSet.has(acc.id)) {
        // 如果是开始同步（状态变为 processing），则重置已采集数为 0
        const updates = { status, progress };
        if (status === 'processing') {
          updates.loaded_msgs = 0;
        }
        console.log('[同步调试] 账号状态变更:', { id: acc.id, name: acc.name, 旧状态: acc.status, 新状态: status });
        return { ...acc, ...updates };
      }
      return acc;
    }));
  };

  // 同步单个账号
  const handleSync = async (accountId, mode = 'fast') => {
    const modeLabel = mode === 'fast' ? '极速同步' : '深度同步';
    console.log(`[同步调试] ========== 单个账号${modeLabel}开始 ==========`);
    console.log(`[同步调试] 账号ID: ${accountId}, 模式: ${mode}`);
    
    // 乐观更新
    updateLocalAccountsStatus([accountId], 'processing', 0);
    
    try {
      console.log(`[同步调试] 发送API请求: POST /accounts/${accountId}/sync`, { mode });
      const result = await accountApi.sync(accountId, mode);
      console.log(`[同步调试] API响应成功:`, result);
      // 减少等待时间，因为我们已经乐观更新了状态
      setTimeout(fetchAccounts, 200);
    } catch (err) {
      console.error(`[同步调试] ${modeLabel}失败:`, err);
      console.error('[同步调试] 错误详情:', {
        message: err.message,
        status: err.status,
        errorCode: err.errorCode,
        data: err.data
      });
      setError('同步失败');
      // 失败后恢复状态或重新获取
      fetchAccounts();
    }
  };

  // 批量同步
  const handleBatchSync = async (mode = 'fast') => {
    const modeLabel = mode === 'fast' ? '极速同步' : '深度同步';
    console.log(`[同步调试] ========== 批量${modeLabel}开始 ==========`);
    console.log('[同步调试] 当前选中的账号IDs:', Array.from(selectedIds));
    console.log('[同步调试] 选中数量:', selectedIds.size);
    
    // 强制使用 Set 来过滤重复 ID，确保只同步选中的账号
    const idsToSync = selectedIds.size > 0 ? Array.from(selectedIds) : [];
    
    // 如果没有选中任何账号，则询问是否同步全部（这里修改逻辑：如果没有选中，则不做任何操作或者提示用户）
    // 为了防止误操作导致同步所有账号，我们这里强制要求必须选中账号
    // 如果需要同步全部，请使用单独的"同步全部"按钮
    
    if (idsToSync.length === 0) {
        console.log('[同步调试] 未选中账号，询问是否同步全部');
        // 原逻辑是如果没有选中，则同步全部，这可能导致用户疑惑
        // 修改为：如果没选中，则提示用户，或者调用 handleSyncAll 但必须有明确意图
        // 鉴于用户反馈"只点了一行"，这里可能是前端逻辑问题
        // 如果是单行操作，不应该走 handleBatchSync，而是 handleSync
        // 检查调用处：如果是单行按钮，调用的是 handleSync(account.id)
        // 如果是顶部按钮，调用 handleBatchSync
        // 顶部按钮逻辑：如果 selectedIds 为空，之前的逻辑是 syncAll，这确实会导致"没选中任何行"时点击"批量同步"变成"同步全部"
        // 让我们修正这个行为：如果没有选中，则什么都不做，或者 alert 提示
        if (!confirm('您未选中任何账号。是否要同步所有账号？')) {
            console.log('[同步调试] 用户取消同步全部');
            return;
        }
        console.log('[同步调试] 用户确认同步全部，转到 handleSyncAll');
        return handleSyncAll(mode);
    }
    
    console.log('[同步调试] 准备同步的账号IDs:', idsToSync);
    
    // 乐观更新
    updateLocalAccountsStatus(idsToSync, 'processing', 0);
    setLoading(true);
    
    try {
      console.log('[同步调试] 发送API请求: POST /accounts/sync-batch', { ids: idsToSync, mode });
      const result = await accountApi.batchSync(idsToSync, mode);
      console.log('[同步调试] 批量同步API响应成功:', result);
      // 清空选择，避免误操作
      setSelectedIds(new Set());
      setTimeout(fetchAccounts, 500);
    } catch (err) {
      console.error(`[同步调试] 批量${modeLabel}失败:`, err);
      console.error('[同步调试] 错误详情:', {
        message: err.message,
        status: err.status,
        errorCode: err.errorCode,
        data: err.data
      });
      setError('批量同步失败');
      fetchAccounts();
    } finally {
      setLoading(false);
    }
  };

  // 同步全部
  const handleSyncAll = async (mode = 'fast') => {
    const modeLabel = mode === 'fast' ? '极速同步' : '深度同步';
    console.log(`[同步调试] ========== 同步全部(${modeLabel})开始 ==========`);
    console.log('[同步调试] 当前账号列表:', accounts.map(acc => ({ id: acc.id, name: acc.name, status: acc.status })));
    
    // 乐观更新所有账号
    const allIds = accounts.map(acc => acc.id);
    console.log('[同步调试] 全部账号IDs:', allIds);
    updateLocalAccountsStatus(allIds, 'processing', 0);
    setLoading(true);
    
    try {
      console.log('[同步调试] 发送API请求: POST /accounts/sync-all', { mode });
      const result = await accountApi.syncAll(mode);
      console.log('[同步调试] 同步全部API响应成功:', result);
      setTimeout(fetchAccounts, 500);
    } catch (err) {
      console.error(`[同步调试] 同步全部(${modeLabel})失败:`, err);
      console.error('[同步调试] 错误详情:', {
        message: err.message,
        status: err.status,
        errorCode: err.errorCode,
        data: err.data
      });
      setError('同步失败');
      fetchAccounts();
    } finally {
      setLoading(false);
    }
  };

  // 停止同步
  const handleStopSync = async () => {
    console.log('[同步调试] ========== 停止同步请求 ==========');
    if (!confirm('确定要停止当前正在进行的同步任务吗？')) return;
    
    try {
      console.log('[同步调试] 发送API请求: POST /accounts/stop-sync');
      const result = await accountApi.stopSync();
      console.log('[同步调试] 停止同步成功:', result);
      setError(null);
      // 立即刷新一次状态，并在之后继续轮询
      setTimeout(fetchAccounts, 500);
    } catch (err) {
      console.error('[同步调试] 停止同步失败:', err);
      setError('停止同步失败');
    }
  };

  // 补齐缺失数据（发布时间等）
  const handleFixMissing = async (accountId) => {
    console.log('[同步调试] ========== 补齐缺失数据 ==========');
    console.log(`[同步调试] 账号ID: ${accountId}`);
    
    // 乐观更新
    updateLocalAccountsStatus([accountId], 'processing', 0);
    
    try {
      const result = await accountApi.fixMissing(accountId, false);
      console.log('[同步调试] 补齐缺失数据成功:', result);
      if (result.missing_count === 0) {
        alert('该博主的所有笔记都已有完整的发布时间');
        fetchAccounts();
        return;
      }
      // 减少等待时间，因为我们已经乐观更新了状态
      setTimeout(fetchAccounts, 200);
    } catch (err) {
      console.error('[同步调试] 补齐缺失数据失败:', err);
      setError('补齐缺失数据失败');
      fetchAccounts();
    }
  };

  // 批量导入（文件上传）
  const handleBatchImport = () => {
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
          // CSV 或 TXT，每行一个 user_id
          userIds = text.split('\n').map(line => line.trim()).filter(Boolean);
        }
        
        if (userIds.length === 0) {
          alert('文件中没有找到有效的用户 ID');
          return;
        }
        
        // 逐个添加
        let added = 0;
        for (const userId of userIds) {
          try {
            await accountApi.add({ user_id: userId });
            added++;
          } catch (err) {
            // 忽略重复添加的错误
            if (err.status !== 409) {
              console.error(`Failed to add ${userId}:`, err);
            }
          }
        }
        
        alert(`成功导入 ${added} 个账号`);
        fetchAccounts();
      } catch (err) {
        console.error('Import failed:', err);
        alert('导入失败: ' + err.message);
      }
    };
    input.click();
  };

  // 批量导出
  const handleBatchExport = () => {
    const exportData = selectedIds.size > 0 
      ? accounts.filter(acc => selectedIds.has(acc.id))
      : accounts;
    
    if (exportData.length === 0) {
      alert('没有可导出的数据');
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
  };

  const isProcessing = accounts.some(acc => acc.status === 'processing' || acc.status === 'pending');

  return (
    <div className="flex-1 bg-gray-50 p-6 overflow-auto">
      {/* 错误提示 */}
      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700">
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">×</button>
        </div>
      )}
      
      <div className="bg-white rounded-lg shadow-sm border">
        {/* 操作栏 */}
        <div className="p-4 border-b flex flex-wrap gap-3 items-center">
          <button 
            onClick={onAddClick}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm flex items-center gap-2"
          >
            <span>+ 添加</span>
          </button>
          
          <div className="h-6 w-px bg-gray-300 mx-1"></div>
          
          <button 
            onClick={handleBatchImport}
            className="px-3 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
          >
            <Upload className="w-3 h-3" /> 导入
          </button>
          
          <button 
            onClick={handleBatchExport}
            className="px-3 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
          >
            <Download className="w-3 h-3" /> 导出
          </button>
          
          <button 
            onClick={handleDelete}
            className="px-3 py-2 bg-red-50 text-red-600 rounded hover:bg-red-100 text-sm flex items-center gap-1"
            disabled={selectedIds.size === 0}
          >
            <Trash2 className="w-3 h-3" /> 删除
          </button>
          
          <div className="h-6 w-px bg-gray-300 mx-1"></div>
          
          {/* 同步控制区 */}
          {isProcessing ? (
             <button 
               onClick={handleStopSync}
               className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 text-sm flex items-center gap-2 animate-pulse"
             >
               <StopCircle className="w-4 h-4" /> 停止同步
             </button>
          ) : (
            <>
              <button 
                onClick={() => handleBatchSync('fast')}
                className="px-4 py-2 bg-green-100 text-green-700 rounded hover:bg-green-200 text-sm flex items-center gap-1 border border-green-200"
                disabled={loading}
                title="只更新点赞数，不采集发布时间/收藏/评论/转发等详情数据"
              >
                <Zap className="w-4 h-4" /> 
                {selectedIds.size > 0 ? `极速同步 (${selectedIds.size})` : '极速同步全部'}
              </button>
              
              <button 
                onClick={() => handleBatchSync('deep')}
                className="px-4 py-2 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 text-sm flex items-center gap-1 border border-blue-200"
                disabled={loading}
                title="采集完整数据（发布时间/收藏/评论/转发/图集），缺失数据会自动补齐"
              >
                <Database className="w-4 h-4" /> 
                {selectedIds.size > 0 ? `深度同步 (${selectedIds.size})` : '深度同步全部'}
              </button>
            </>
          )}
          
          <button 
            onClick={handleReset} 
            className="px-3 py-2 text-gray-400 hover:text-red-500 rounded text-sm flex items-center gap-1 ml-auto"
            title="清空所有数据"
          >
            <Trash2 className="w-3 h-3" /> 清空
          </button>
        </div>

        {/* 表格 */}
        <div className="w-full overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-gray-500 bg-gray-50 border-b">
              <tr>
                <th className="p-4 w-10">
                  <input 
                    type="checkbox" 
                    checked={selectedIds.size === filteredAccounts.length && filteredAccounts.length > 0} 
                    onChange={toggleSelectAll}
                    className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                  />
                </th>
                <th className="p-4">#</th>
                <th className="p-4">头像</th>
                <th className="p-4">名称</th>
                <th className="p-4">粉丝数</th>
                <th className="p-4">最后同步时间</th>
                <th className="p-4 text-center">笔记总数</th>
                <th className="p-4 text-center">已采集数</th>
                <th className="p-4">采集进度</th>
                <th className="p-4 text-center">状态</th>
                <th className="p-4 text-center">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredAccounts.length === 0 ? (
                <tr>
                  <td colSpan="10" className="p-8 text-center text-gray-400">
                    {loading ? '加载中...' : '暂无数据，点击"添加"按钮添加博主'}
                  </td>
                </tr>
              ) : (
                filteredAccounts.map((account, index) => (
                  <tr key={account.id} className="border-b hover:bg-gray-50">
                    <td className="p-4">
                      <input 
                        type="checkbox" 
                        checked={selectedIds.has(account.id)} 
                        onChange={() => toggleSelect(account.id)}
                        className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                    </td>
                    <td className="p-4 text-gray-500">{index + 1}</td>
                    <td className="p-4">
                      <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500 overflow-hidden">
                        {account.avatar ? (
                          <img src={account.avatar} alt={account.name} className="w-full h-full object-cover" />
                        ) : (
                          'IMG'
                        )}
                      </div>
                    </td>
                    <td className="p-4 font-medium">{account.name || account.user_id}</td>
                    <td className="p-4">{account.fans !== undefined ? account.fans : '-'}</td>
                    <td className="p-4 text-gray-500">
                      {account.last_sync ? new Date(account.last_sync).toLocaleString() : '-'}
                    </td>
                    <td className="p-4 text-center">{account.total_msgs || 0}</td>
                    <td className="p-4 text-center">{account.loaded_msgs || 0}</td>
                    <td className="p-4 w-48">
                      <div className="flex flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <div className="flex-1 h-2 bg-blue-100 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-blue-500 rounded-full transition-all duration-300"
                              style={{ width: `${account.status === 'completed' ? 100 : (account.progress || 0)}%` }}
                            />
                          </div>
                          <span className="text-xs text-gray-500 w-8 text-right">{account.status === 'completed' ? 100 : (account.progress || 0)}%</span>
                        </div>
                        {account.status === 'processing' && (
                          <div className="text-xs text-blue-500 transform scale-90 origin-left animate-pulse">
                            {(account.progress || 0) === 0 ? '正在启动...' : '同步中...'}
                          </div>
                        )}
                      </div>
                    </td>
                    <td className="p-4 text-center">
                      <div className="flex flex-col items-center gap-1">
                        {account.status === 'completed' ? (
                          <CheckCircle className="w-4 h-4 text-green-500" title="已完成" />
                        ) : account.status === 'failed' ? (
                          <div className="group relative">
                            <AlertCircle className="w-4 h-4 text-red-500 cursor-help" />
                            {account.error_message && (
                              <div className="absolute z-10 opacity-0 invisible group-hover:opacity-100 group-hover:visible hover:opacity-100 hover:visible transition-opacity duration-150 bg-gray-800 text-white text-xs rounded py-2 px-3 -left-32 bottom-full mb-2 w-64 whitespace-normal select-text cursor-text shadow-lg">
                                {account.error_message}
                                <div className="absolute left-1/2 -bottom-1 transform -translate-x-1/2 w-2 h-2 bg-gray-800 rotate-45"></div>
                              </div>
                            )}
                          </div>
                        ) : (account.status === 'processing' || account.status === 'pending') ? (
                          <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" title="同步中" />
                        ) : (
                          <Circle className="w-4 h-4 text-gray-300" title="待同步" />
                        )}
                        <span className="text-xs text-gray-400">
                          {account.status === 'completed' ? '完成' : 
                           account.status === 'failed' ? '失败' : 
                           account.status === 'processing' ? '同步中' : 
                           account.status === 'pending' ? '准备中' : '待同步'}
                        </span>
                      </div>
                    </td>
                    <td className="p-4 text-center">
                      <div className="flex gap-1 justify-center">
                        <button 
                          className="p-1 hover:bg-green-100 rounded text-green-600 disabled:opacity-50"
                          onClick={() => handleSync(account.id, 'fast')}
                          disabled={account.status === 'processing'}
                          title="极速同步"
                        >
                          <Zap className="w-4 h-4" />
                        </button>
                        <button 
                          className="p-1 hover:bg-blue-100 rounded text-blue-600 disabled:opacity-50"
                          onClick={() => handleSync(account.id, 'deep')}
                          disabled={account.status === 'processing'}
                          title="深度同步"
                        >
                          <Database className="w-4 h-4" />
                        </button>
                        <button 
                          className="p-1 hover:bg-orange-100 rounded text-orange-600 disabled:opacity-50"
                          onClick={() => handleFixMissing(account.id)}
                          disabled={account.status === 'processing'}
                          title="补齐缺失数据（发布时间等）"
                        >
                          <Wrench className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

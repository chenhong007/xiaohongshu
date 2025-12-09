import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, CheckCircle, Circle, Trash2, Upload, Download, AlertCircle } from 'lucide-react';
import { accountApi } from '../services';

export const ContentArea = ({ activeTab, searchTerm, onAddClick, refreshTrigger, onRefresh }) => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [error, setError] = useState(null);

  // 过滤账号
  const filteredAccounts = accounts.filter(acc => 
    acc.name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // 获取账号列表
  const fetchAccounts = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    
    try {
      const data = await accountApi.getAll();
      setAccounts(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to fetch accounts:', err);
      if (!silent) setError('获取账号列表失败');
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  // 轮询更新处理中的账号状态
  useEffect(() => {
    const isProcessing = accounts.some(acc => acc.status === 'processing');
    if (isProcessing) {
      const timer = setInterval(() => fetchAccounts(true), 2000);
      return () => clearInterval(timer);
    }
  }, [accounts, fetchAccounts]);

  // 初始加载和刷新
  useEffect(() => {
    fetchAccounts();
  }, [refreshTrigger, fetchAccounts]);

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

  // 同步单个账号
  const handleSync = async (accountId) => {
    try {
      await accountApi.sync(accountId);
      setTimeout(fetchAccounts, 500);
    } catch (err) {
      console.error('Sync failed:', err);
      setError('同步失败');
    }
  };

  // 批量同步
  const handleBatchSync = async () => {
    if (selectedIds.size === 0) {
      return handleSyncAll();
    }
    
    setLoading(true);
    try {
      await accountApi.batchSync(Array.from(selectedIds));
      setTimeout(fetchAccounts, 1000);
      setSelectedIds(new Set());
    } catch (err) {
      console.error('Batch sync failed:', err);
      setError('批量同步失败');
    } finally {
      setLoading(false);
    }
  };

  // 同步全部
  const handleSyncAll = async () => {
    setLoading(true);
    try {
      await accountApi.syncAll();
      setTimeout(fetchAccounts, 1000);
    } catch (err) {
      console.error('Sync all failed:', err);
      setError('同步失败');
    } finally {
      setLoading(false);
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

  const isProcessing = accounts.some(acc => acc.status === 'processing');

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
        <div className="p-4 border-b flex flex-wrap gap-3">
          <button 
            onClick={onAddClick}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm flex items-center gap-2"
          >
            <span>+ 添加</span>
          </button>
          
          <button 
            onClick={handleBatchImport}
            className="px-4 py-2 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 text-sm flex items-center gap-1"
          >
            <Upload className="w-3 h-3" /> 批量导入
          </button>
          
          <button 
            onClick={handleBatchExport}
            className="px-4 py-2 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 text-sm flex items-center gap-1"
          >
            <Download className="w-3 h-3" /> 批量导出
          </button>
          
          <button 
            onClick={handleDelete}
            className="px-4 py-2 bg-red-100 text-red-600 rounded hover:bg-red-200 text-sm flex items-center gap-1"
            disabled={selectedIds.size === 0}
          >
            <Trash2 className="w-3 h-3" /> 删除 {selectedIds.size > 0 && `(${selectedIds.size})`}
          </button>
          
          <button 
            onClick={handleBatchSync}
            className="px-4 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
            disabled={loading || isProcessing}
          >
            <RefreshCw className={`w-3 h-3 ${loading || isProcessing ? 'animate-spin' : ''}`} />
            {selectedIds.size > 0 ? `同步选中 (${selectedIds.size})` : '同步全部'}
          </button>
          
          <button 
            onClick={handleReset} 
            className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 text-sm flex items-center gap-1 ml-auto"
          >
            <Trash2 className="w-3 h-3" /> 清空数据库
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
                    <td className="p-4 text-gray-500">
                      {account.last_sync ? new Date(account.last_sync).toLocaleString() : '-'}
                    </td>
                    <td className="p-4 text-center">{account.total_msgs || 0}</td>
                    <td className="p-4 text-center">{account.loaded_msgs || 0}</td>
                    <td className="p-4 w-48">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-blue-100 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-blue-500 rounded-full transition-all duration-300"
                            style={{ width: `${account.progress || 0}%` }}
                          />
                        </div>
                        <span className="text-xs text-gray-500 w-10">{account.progress || 0}%</span>
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
                        ) : account.status === 'processing' ? (
                          <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" title="同步中" />
                        ) : (
                          <Circle className="w-4 h-4 text-gray-300" title="待同步" />
                        )}
                        <span className="text-xs text-gray-400">
                          {account.status === 'completed' ? '完成' : 
                           account.status === 'failed' ? '失败' : 
                           account.status === 'processing' ? '同步中' : '待同步'}
                        </span>
                      </div>
                    </td>
                    <td className="p-4 text-center">
                      <button 
                        className="p-1 hover:bg-gray-100 rounded text-blue-500 disabled:opacity-50"
                        onClick={() => handleSync(account.id)}
                        disabled={account.status === 'processing'}
                        title="同步/采集数据"
                      >
                        <RefreshCw className={`w-4 h-4 ${account.status === 'processing' ? 'animate-spin' : ''}`} />
                      </button>
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

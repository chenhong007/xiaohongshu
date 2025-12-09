import React, { useState, useEffect } from 'react';
import { RefreshCw, CheckCircle, Circle, Trash2 } from 'lucide-react';

export const ContentArea = ({ activeTab, searchTerm, onAddClick, refreshTrigger }) => {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchAccounts = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/accounts');
      if (res.ok) {
        const data = await res.json();
        setAccounts(data);
      }
    } catch (error) {
      console.error('Failed to fetch accounts:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAccounts();
  }, [refreshTrigger]);

  const handleReset = async () => {
    if (!confirm('确定要清空所有数据库数据吗？这将无法恢复。')) return;
    try {
      const res = await fetch('/api/reset', { method: 'POST' });
      if (res.ok) {
        fetchAccounts();
      }
    } catch (error) {
      console.error('Failed to reset db:', error);
    }
  };

  const handleSync = async (accountId) => {
    try {
      const res = await fetch(`/api/accounts/${accountId}/sync`, { method: 'POST' });
      if (res.ok) {
        // Trigger refresh to update status
        fetchAccounts();
      } else {
        console.error('Sync failed');
      }
    } catch (error) {
      console.error('Sync failed:', error);
    }
  };

  const handleSyncAll = async () => {
    if (!confirm('确定要同步所有博主数据吗？这可能需要一些时间。')) return;
    setLoading(true);
    try {
      const res = await fetch('/api/accounts/sync-all', { method: 'POST' });
      if (res.ok) {
        // Wait a bit for status to update
        setTimeout(fetchAccounts, 1000);
      } else {
        console.error('Sync all failed');
      }
    } catch (error) {
      console.error('Sync all failed:', error);
    } finally {
        setLoading(false);
    }
  };

  const filteredAccounts = accounts.filter(acc => 
    acc.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex-1 bg-gray-50 p-6 overflow-auto">
      <div className="bg-white rounded-lg shadow-sm border">
        {/* Header Actions */}
        <div className="p-4 border-b flex gap-3">
            <button 
                onClick={onAddClick}
                className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm flex items-center gap-2"
            >
                <span>+ 添加</span>
            </button>
            <button className="px-4 py-2 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 text-sm">
                批量导入
            </button>
            <button className="px-4 py-2 bg-blue-100 text-blue-600 rounded hover:bg-blue-200 text-sm">
                批量导出
            </button>
            <button className="px-4 py-2 bg-red-100 text-red-600 rounded hover:bg-red-200 text-sm">
                删除
            </button>
            <button 
                onClick={handleSyncAll}
                className="px-4 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
                disabled={loading}
            >
                <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> 同步
            </button>
            <button onClick={handleReset} className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 text-sm flex items-center gap-1 ml-auto">
                <Trash2 className="w-3 h-3" /> 清空数据库
            </button>
        </div>

        {/* Table */}
        <div className="w-full overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-gray-500 bg-gray-50 border-b">
              <tr>
                <th className="p-4">#</th>
                <th className="p-4">头像</th>
                <th className="p-4">名称</th>
                <th className="p-4">最后同步时间</th>
                <th className="p-4 text-center">笔记总数</th>
                <th className="p-4 text-center">已采集笔记数</th>
                <th className="p-4">采集进度</th>
                <th className="p-4 text-center">已采集完成</th>
                <th className="p-4 text-center">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredAccounts.length === 0 ? (
                  <tr>
                      <td colSpan="10" className="p-8 text-center text-gray-400">
                          {loading ? '加载中...' : '暂无数据'}
                      </td>
                  </tr>
              ) : (
                filteredAccounts.map((account, index) => (
                    <tr key={account.id} className="border-b hover:bg-gray-50">
                    <td className="p-4">{index + 1}</td>
                    <td className="p-4">
                        <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500 overflow-hidden">
                             {account.avatar ? <img src={account.avatar} alt={account.name} /> : 'IMG'}
                        </div>
                    </td>
                    <td className="p-4 font-medium">{account.name}</td>
                    <td className="p-4 text-gray-500">{account.last_sync ? new Date(account.last_sync).toLocaleString() : '-'}</td>
                    <td className="p-4 text-center">{account.total_msgs}</td>
                    <td className="p-4 text-center">{account.loaded_msgs}</td>
                    <td className="p-4 w-48">
                        <div className="flex items-center gap-2">
                            <div className="flex-1 h-2 bg-blue-100 rounded-full overflow-hidden">
                                <div 
                                    className="h-full bg-blue-500 rounded-full"
                                    style={{ width: `${account.progress}%` }}
                                />
                            </div>
                            <span className="text-xs text-gray-500">{account.progress}%</span>
                        </div>
                    </td>
                    <td className="p-4 text-center">
                        {account.status === 'completed' ? (
                            <CheckCircle className="w-4 h-4 text-green-500 mx-auto" />
                        ) : (
                            <Circle className="w-4 h-4 text-gray-300 mx-auto" />
                        )}
                    </td>
                    <td className="p-4 text-center">
                        <button 
                            className="p-1 hover:bg-gray-100 rounded text-blue-500"
                            onClick={() => handleSync(account.id)}
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

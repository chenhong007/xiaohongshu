import React, { useState, useEffect, useCallback, useRef } from 'react';
import { RefreshCw, CheckCircle, Circle, Trash2, Upload, Download, AlertCircle, Zap, Database, StopCircle, Wrench, FileText, X, ChevronDown, ChevronUp, Clock, Ban, AlertTriangle, Key, Image as ImageIcon, Wifi, WifiOff } from 'lucide-react';
import { accountApi, authApi, COOKIE_INVALID_EVENT } from '../services';
import syncWebSocket from '../services/websocket';

// 同步日志详情模态框
const SyncLogModal = ({ isOpen, onClose, account }) => {
  const [expandedIssues, setExpandedIssues] = useState(false);
  
  if (!isOpen || !account) return null;
  
  const logs = account.sync_logs;
  if (!logs) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={onClose}>
        <div className="bg-white rounded-lg shadow-xl p-6 max-w-md" onClick={e => e.stopPropagation()}>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">同步日志</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
          </div>
          <p className="text-gray-500 text-center py-8">暂无同步日志数据</p>
        </div>
      </div>
    );
  }
  
  const summary = logs.summary || {};
  const issues = logs.issues || [];
  
  // 问题类型图标和颜色映射
  const issueTypeConfig = {
    rate_limited: { icon: Clock, color: 'text-orange-500', bgColor: 'bg-orange-50', label: '限流' },
    unavailable: { icon: Ban, color: 'text-gray-500', bgColor: 'bg-gray-50', label: '不可用' },
    missing_field: { icon: AlertTriangle, color: 'text-yellow-600', bgColor: 'bg-yellow-50', label: '字段缺失' },
    fetch_failed: { icon: AlertCircle, color: 'text-red-500', bgColor: 'bg-red-50', label: '获取失败' },
    token_refresh: { icon: Key, color: 'text-blue-500', bgColor: 'bg-blue-50', label: 'Token刷新' },
    media_failed: { icon: ImageIcon, color: 'text-purple-500', bgColor: 'bg-purple-50', label: '媒体失败' },
    auth_error: { icon: AlertCircle, color: 'text-red-600', bgColor: 'bg-red-100', label: '认证错误' },
  };
  
  const getIssueConfig = (type) => issueTypeConfig[type] || { icon: AlertCircle, color: 'text-gray-500', bgColor: 'bg-gray-50', label: type };
  
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div 
        className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col" 
        onClick={e => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex justify-between items-center p-4 border-b bg-gray-50">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-500" />
              深度同步日志 - {account.name || account.user_id}
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              {logs.start_time && `开始: ${new Date(logs.start_time).toLocaleString()}`}
              {logs.end_time && ` | 结束: ${new Date(logs.end_time).toLocaleString()}`}
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1">
            <X className="w-5 h-5" />
          </button>
        </div>
        
        {/* 摘要统计 */}
        <div className="p-4 border-b">
          <h4 className="text-sm font-medium text-gray-700 mb-3">同步摘要</h4>
          <div className="grid grid-cols-4 gap-3">
            <div className="bg-blue-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-blue-600">{summary.total || 0}</div>
              <div className="text-xs text-blue-600">总笔记数</div>
            </div>
            <div className="bg-green-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-green-600">{summary.success || 0}</div>
              <div className="text-xs text-green-600">成功获取</div>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-gray-600">{summary.skipped || 0}</div>
              <div className="text-xs text-gray-600">跳过(已有)</div>
            </div>
            <div className="bg-yellow-50 rounded-lg p-3 text-center">
              <div className="text-2xl font-bold text-yellow-600">
                {(summary.rate_limited || 0) + (summary.missing_field || 0) + (summary.fetch_failed || 0)}
              </div>
              <div className="text-xs text-yellow-600">问题数</div>
            </div>
          </div>
          
          {/* 问题详细分类 */}
          {((summary.rate_limited || 0) + (summary.unavailable || 0) + (summary.missing_field || 0) + (summary.fetch_failed || 0) + (summary.token_refresh || 0)) > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {summary.rate_limited > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-1 bg-orange-50 text-orange-600 rounded text-xs">
                  <Clock className="w-3 h-3" /> 限流 {summary.rate_limited}次
                </span>
              )}
              {summary.unavailable > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 text-gray-600 rounded text-xs">
                  <Ban className="w-3 h-3" /> 不可用 {summary.unavailable}条
                </span>
              )}
              {summary.missing_field > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-50 text-yellow-600 rounded text-xs">
                  <AlertTriangle className="w-3 h-3" /> 字段缺失 {summary.missing_field}条
                </span>
              )}
              {summary.fetch_failed > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-1 bg-red-50 text-red-600 rounded text-xs">
                  <AlertCircle className="w-3 h-3" /> 获取失败 {summary.fetch_failed}条
                </span>
              )}
              {summary.token_refresh > 0 && (
                <span className="inline-flex items-center gap-1 px-2 py-1 bg-blue-50 text-blue-600 rounded text-xs">
                  <Key className="w-3 h-3" /> Token刷新 {summary.token_refresh}次
                </span>
              )}
            </div>
          )}
        </div>
        
        {/* 问题列表 */}
        <div className="flex-1 overflow-y-auto p-4">
          <div className="flex justify-between items-center mb-3">
            <h4 className="text-sm font-medium text-gray-700">
              问题详情 ({issues.length}条)
            </h4>
            {issues.length > 5 && (
              <button 
                onClick={() => setExpandedIssues(!expandedIssues)}
                className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1"
              >
                {expandedIssues ? <><ChevronUp className="w-3 h-3" /> 收起</> : <><ChevronDown className="w-3 h-3" /> 展开全部</>}
              </button>
            )}
          </div>
          
          {issues.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-400" />
              <p>没有问题，同步一切正常！</p>
            </div>
          ) : (
            <div className="space-y-2">
              {(expandedIssues ? issues : issues.slice(0, 10)).map((issue, idx) => {
                const config = getIssueConfig(issue.type);
                const IconComponent = config.icon;
                return (
                  <div key={idx} className={`${config.bgColor} rounded-lg p-3 text-sm`}>
                    <div className="flex items-start gap-2">
                      <IconComponent className={`w-4 h-4 ${config.color} mt-0.5 flex-shrink-0`} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className={`font-medium ${config.color}`}>{config.label}</span>
                          {issue.note_id && (
                            <a 
                              href={`https://www.xiaohongshu.com/explore/${issue.note_id}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-xs text-blue-500 hover:underline"
                            >
                              笔记: {issue.note_id.slice(0, 8)}...
                            </a>
                          )}
                          <span className="text-xs text-gray-400">
                            {issue.time && new Date(issue.time).toLocaleTimeString()}
                          </span>
                        </div>
                        {issue.message && (
                          <p className="text-gray-600 text-xs mt-1 break-all">{issue.message}</p>
                        )}
                        {issue.fields && (
                          <p className="text-xs text-gray-500 mt-1">
                            缺失字段: {issue.fields.join(', ')}
                          </p>
                        )}
                        {issue.extra && (
                          <p className="text-xs text-gray-400 mt-1">
                            {issue.extra.reason && `原因: ${issue.extra.reason}`}
                            {issue.extra.retry && ` | 重试次数: ${issue.extra.retry}`}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
              {!expandedIssues && issues.length > 10 && (
                <div className="text-center py-2">
                  <button 
                    onClick={() => setExpandedIssues(true)}
                    className="text-sm text-blue-500 hover:text-blue-700"
                  >
                    还有 {issues.length - 10} 条问题，点击展开
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
        
        {/* 底部 */}
        <div className="p-4 border-t bg-gray-50 flex justify-end">
          <button 
            onClick={onClose}
            className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 text-sm"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
};

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
  
  // 同步日志模态框状态
  const [logModalOpen, setLogModalOpen] = useState(false);
  const [selectedAccountForLog, setSelectedAccountForLog] = useState(null);
  
  // 记录上一次的账号状态，用于检测变化
  const prevAccountsRef = useRef([]);
  
  // 记录已输出过日志的账号ID和日志时间戳，避免重复输出
  const loggedSyncRef = useRef(new Map());

  // 过滤账号
  const filteredAccounts = accounts.filter(acc => 
    acc.name?.toLowerCase().includes(searchTerm.toLowerCase())
  );

  // 触发 Cookie 失效事件
  const emitCookieInvalid = () => {
    window.dispatchEvent(new CustomEvent(COOKIE_INVALID_EVENT));
  };

  /**
   * 将同步日志输出到 console（用于分析问题）
   * @param {Object} account - 账号对象
   */
  const logSyncDetailsToConsole = useCallback((account) => {
    if (!account?.sync_logs) return;
    
    const logs = account.sync_logs;
    const summary = logs.summary || {};
    const issues = logs.issues || [];
    
    // 使用 console.group 进行分组输出，便于阅读
    console.group(
      `%c📋 深度同步日志 - ${account.name || account.user_id}`,
      'color: #3B82F6; font-weight: bold; font-size: 14px;'
    );
    
    // 输出同步时间信息
    console.log(
      '%c⏰ 同步时间',
      'color: #6B7280; font-weight: bold;',
      {
        开始时间: logs.start_time ? new Date(logs.start_time).toLocaleString() : '未知',
        结束时间: logs.end_time ? new Date(logs.end_time).toLocaleString() : '未知',
        同步模式: logs.sync_mode || 'deep'
      }
    );
    
    // 输出摘要统计
    console.log(
      '%c📊 同步摘要',
      'color: #10B981; font-weight: bold;',
      {
        笔记总数: summary.total || 0,
        成功获取: summary.success || 0,
        跳过已有: summary.skipped || 0,
        限流次数: summary.rate_limited || 0,
        不可用笔记: summary.unavailable || 0,
        字段缺失: summary.missing_field || 0,
        获取失败: summary.fetch_failed || 0,
        Token刷新: summary.token_refresh || 0,
        媒体失败: summary.media_failed || 0
      }
    );
    
    // 如果有问题，输出问题详情
    const problemCount = (summary.rate_limited || 0) + (summary.missing_field || 0) + 
                         (summary.fetch_failed || 0) + (summary.unavailable || 0);
    
    if (problemCount > 0 && issues.length > 0) {
      console.group(
        `%c⚠️ 问题详情 (共 ${issues.length} 条)`,
        'color: #F59E0B; font-weight: bold;'
      );
      
      // 按类型分组输出问题
      const issuesByType = {};
      issues.forEach(issue => {
        const type = issue.type || 'unknown';
        if (!issuesByType[type]) {
          issuesByType[type] = [];
        }
        issuesByType[type].push(issue);
      });
      
      // 问题类型的中文名称和颜色
      const typeConfig = {
        rate_limited: { name: '🚫 限流', color: '#F97316' },
        unavailable: { name: '🚷 笔记不可用', color: '#6B7280' },
        missing_field: { name: '⚠️ 字段缺失', color: '#EAB308' },
        fetch_failed: { name: '❌ 获取失败', color: '#EF4444' },
        token_refresh: { name: '🔑 Token刷新', color: '#3B82F6' },
        media_failed: { name: '🖼️ 媒体下载失败', color: '#8B5CF6' },
        auth_error: { name: '🔒 认证错误', color: '#DC2626' }
      };
      
      Object.entries(issuesByType).forEach(([type, typeIssues]) => {
        const config = typeConfig[type] || { name: type, color: '#6B7280' };
        
        console.group(`%c${config.name} (${typeIssues.length}条)`, `color: ${config.color}; font-weight: bold;`);
        
        // 限制输出数量，避免 console 过于冗长
        const displayIssues = typeIssues.slice(0, 20);
        displayIssues.forEach((issue, idx) => {
          const noteLink = issue.note_id 
            ? `https://www.xiaohongshu.com/explore/${issue.note_id}`
            : null;
          
          console.log(
            `%c[${idx + 1}]`,
            'color: #9CA3AF;',
            {
              笔记ID: issue.note_id || '无',
              笔记链接: noteLink || '无',
              时间: issue.time ? new Date(issue.time).toLocaleTimeString() : '未知',
              消息: issue.message || '无',
              缺失字段: issue.fields?.join(', ') || '无',
              额外信息: issue.extra || null
            }
          );
        });
        
        if (typeIssues.length > 20) {
          console.log(`%c... 还有 ${typeIssues.length - 20} 条同类问题未显示`, 'color: #9CA3AF; font-style: italic;');
        }
        
        console.groupEnd();
      });
      
      console.groupEnd(); // 问题详情
    } else {
      console.log('%c✅ 没有问题，同步一切正常！', 'color: #10B981; font-weight: bold;');
    }
    
    // 输出原始日志数据（方便复制分析）
    console.log('%c📄 原始日志数据', 'color: #6B7280; font-weight: bold;', logs);
    
    console.groupEnd(); // 深度同步日志
  }, []);

  /**
   * 检测账号同步状态变化，输出日志到 console
   */
  useEffect(() => {
    accounts.forEach(acc => {
      // 只关注有 sync_logs 的账号
      if (!acc.sync_logs) return;
      
      // 找到之前的状态
      const prevAcc = prevAccountsRef.current.find(p => p.id === acc.id);
      
      // 检测状态变化：从 processing 变为 completed 或 failed
      const statusChanged = prevAcc && 
        (prevAcc.status === 'processing' || prevAcc.status === 'pending') &&
        (acc.status === 'completed' || acc.status === 'failed');
      
      // 检测是否有新的日志（通过 end_time 判断）
      const logEndTime = acc.sync_logs.end_time;
      const lastLoggedTime = loggedSyncRef.current.get(acc.id);
      const hasNewLog = logEndTime && logEndTime !== lastLoggedTime;
      
      // 如果状态变化或有新日志，输出到 console
      if ((statusChanged || hasNewLog) && logEndTime) {
        logSyncDetailsToConsole(acc);
        loggedSyncRef.current.set(acc.id, logEndTime);
      }
    });
  }, [accounts, logSyncDetailsToConsole]);

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

  // WebSocket 连接状态
  const [wsConnected, setWsConnected] = useState(false);
  const wsInitializedRef = useRef(false);

  // 初始化 WebSocket 连接
  useEffect(() => {
    if (wsInitializedRef.current) return;
    wsInitializedRef.current = true;

    const initWebSocket = async () => {
      const connected = await syncWebSocket.connect();
      setWsConnected(connected);
      
      if (connected) {
        console.log('[WebSocket] Connected, subscribing to all sync updates');
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

  // WebSocket 事件监听
  useEffect(() => {
    if (!wsConnected) return;

    // Handle progress updates
    const unsubProgress = syncWebSocket.on('progress', (data) => {
      console.log('[WebSocket] Progress update:', data);
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
    });

    // Handle sync completion
    const unsubCompleted = syncWebSocket.on('completed', (data) => {
      console.log('[WebSocket] Sync completed:', data);
      // Fetch full account data including sync_logs
      setTimeout(() => fetchAccounts(true), 500);
    });

    // Handle log messages (optional, for debugging)
    const unsubLog = syncWebSocket.on('log', (data) => {
      if (data.level === 'error' || data.level === 'warn') {
        console.log(`[WebSocket] Sync log [${data.level}]:`, data.message);
      }
    });

    return () => {
      unsubProgress();
      unsubCompleted();
      unsubLog();
    };
  }, [wsConnected, fetchAccounts, setAccounts]);

  // 轮询回退（当 WebSocket 不可用时）
  useEffect(() => {
    // Skip polling if WebSocket is connected
    if (wsConnected) return;

    const processingAccounts = accounts.filter(acc => acc.status === 'processing' || acc.status === 'pending');
    const isProcessing = processingAccounts.length > 0;
    
    if (isProcessing) {
      // 只显示正在处理的账号，格式更简洁
      const summary = processingAccounts.map(acc => 
        `${acc.name || acc.user_id}: ${acc.progress || 0}% (${acc.loaded_msgs || 0}/${acc.total_msgs || 0})`
      ).join(', ');
      console.log(`[轮询模式] 正在处理 ${processingAccounts.length} 个账号:`, summary);
      
      // 【性能优化】使用轻量级状态 API，避免序列化 sync_logs 等大字段
      const timer = setInterval(async () => {
        try {
          // 使用轻量级 API 只获取状态字段
          const statusList = await accountApi.getStatus();
          
          // 检查是否有账号从 processing/pending 变为 completed/failed
          const statusMap = new Map(statusList.map(s => [s.id, s]));
          const justCompleted = accounts.some(acc => {
            const newStatus = statusMap.get(acc.id);
            return newStatus && 
              (acc.status === 'processing' || acc.status === 'pending') &&
              (newStatus.status === 'completed' || newStatus.status === 'failed');
          });
          
          // 合并状态到现有账号数据
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
          
          // 如果有账号刚完成，延迟获取完整数据（包含 sync_logs）
          if (justCompleted) {
            console.log('[轮询模式] 检测到同步完成，获取完整数据');
            setTimeout(() => fetchAccounts(true), 500);
          }
        } catch (err) {
          console.error('[轮询模式] 获取状态失败:', err);
        }
      }, 4000);
      
      return () => {
        console.log('[轮询模式] 停止轮询');
        clearInterval(timer);
      };
    }
  }, [accounts, fetchAccounts, setAccounts, wsConnected]);

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
          
          {/* WebSocket 连接状态指示器 */}
          <div 
            className={`ml-auto flex items-center gap-1 px-2 py-1 rounded text-xs ${
              wsConnected 
                ? 'bg-green-50 text-green-600' 
                : 'bg-gray-50 text-gray-400'
            }`}
            title={wsConnected ? 'WebSocket 实时推送已连接' : '使用轮询模式'}
          >
            {wsConnected ? (
              <>
                <Wifi className="w-3 h-3" />
                <span>实时</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3 h-3" />
                <span>轮询</span>
              </>
            )}
          </div>

          <button 
            onClick={handleReset} 
            className="px-3 py-2 text-gray-400 hover:text-red-500 rounded text-sm flex items-center gap-1"
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
                          <>
                            {/* 完成状态：检查是否有问题 */}
                            {account.sync_logs?.summary && (
                              (account.sync_logs.summary.rate_limited || 0) + 
                              (account.sync_logs.summary.missing_field || 0) + 
                              (account.sync_logs.summary.fetch_failed || 0)
                            ) > 0 ? (
                              <div 
                                className="flex items-center gap-1 cursor-pointer hover:bg-yellow-100 rounded px-1"
                                onClick={() => { setSelectedAccountForLog(account); setLogModalOpen(true); }}
                                title="同步完成但有问题，点击查看详情"
                              >
                                <AlertTriangle className="w-4 h-4 text-yellow-500" />
                                <span className="text-xs text-yellow-600">有问题</span>
                              </div>
                            ) : (
                              <CheckCircle className="w-4 h-4 text-green-500" title="已完成" />
                            )}
                          </>
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
                        {/* 查看日志按钮 - 仅当有日志时显示 */}
                        {account.sync_logs && (
                          <button
                            onClick={() => { setSelectedAccountForLog(account); setLogModalOpen(true); }}
                            className="text-xs text-blue-500 hover:text-blue-700 hover:underline flex items-center gap-0.5"
                            title="查看同步日志详情"
                          >
                            <FileText className="w-3 h-3" />
                            日志
                          </button>
                        )}
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
      
      {/* 同步日志模态框 */}
      <SyncLogModal 
        isOpen={logModalOpen} 
        onClose={() => { setLogModalOpen(false); setSelectedAccountForLog(null); }} 
        account={selectedAccountForLog} 
      />
    </div>
  );
};

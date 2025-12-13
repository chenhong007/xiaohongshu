import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { AlertTriangle, X, Clock } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { ContentArea } from './components/ContentArea';
import { DownloadPage } from './components/DownloadPage';
import { searchApi, accountApi } from './services';

// SSE 日志颜色映射
const LOG_COLORS = {
  info: 'color: #3B82F6; font-weight: bold;',
  warn: 'color: #F59E0B; font-weight: bold;',
  error: 'color: #EF4444; font-weight: bold;',
  debug: 'color: #6B7280;',
};

// Cookie 状态事件名
const COOKIE_STATUS_EVENT = 'cookie-status-changed';

// Cookie 状态类型
const COOKIE_STATUS = {
  INVALID: 'invalid',      // Cookie 失效
  RATE_LIMITED: 'rate_limited',  // 被限流
  VALID: 'valid',          // Cookie 有效
};

function App() {
  const [searchTerm, setSearchTerm] = useState('');
  const [isSearchVisible, setIsSearchVisible] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  
  // ========== 账号数据缓存（提升到 App 层级避免页面切换时丢失） ==========
  const [accounts, setAccounts] = useState([]);
  const [accountsLoading, setAccountsLoading] = useState(false);
  const [accountsError, setAccountsError] = useState(null);
  const accountsLoadedRef = useRef(false);  // 标记是否已加载过
  
  // ========== Cookie 状态（用于全局显示限流/失效警告） ==========
  const [cookieStatus, setCookieStatus] = useState(null);
  // cookieStatus: { status: 'rate_limited' | 'invalid', message: string, extra: object, timestamp: number }
  
  // SSE 连接引用
  const eventSourceRef = useRef(null);

  // 获取账号列表
  const fetchAccounts = useCallback(async (silent = false) => {
    // 静默刷新时不输出日志，减少噪音
    if (!silent) {
      console.log('[同步调试] fetchAccounts 被调用');
    }
    
    // 如果已有缓存数据，静默刷新（不显示 loading）
    if (!silent && accounts.length === 0) {
      setAccountsLoading(true);
    }
    setAccountsError(null);
    
    try {
      const data = await accountApi.getAll();
      const accountsData = Array.isArray(data) ? data : [];
      
      // 只在非静默模式下输出日志，或有正在处理的账号时输出
      const processingAccounts = accountsData.filter(a => a.status === 'processing' || a.status === 'pending');
      
      if (!silent) {
        // 非静默模式：输出状态统计
        const statusSummary = accountsData.reduce((acc, a) => {
          acc[a.status || 'unknown'] = (acc[a.status || 'unknown'] || 0) + 1;
          return acc;
        }, {});
        console.log('[同步调试] 账号列表, 状态统计:', statusSummary);
      }
      
      // 只打印正在处理的账号状态（无论是否静默）
      if (processingAccounts.length > 0) {
        processingAccounts.forEach(acc => {
          console.log(`[同步调试] 正在处理: ${acc.name || acc.user_id} - ${acc.progress}% (${acc.loaded_msgs}/${acc.total_msgs})`);
        });
      }
      
      setAccounts(accountsData);
      accountsLoadedRef.current = true;
    } catch (err) {
      console.error('[同步调试] 获取账号列表失败:', err);
      if (!silent && accounts.length === 0) {
        setAccountsError('获取账号列表失败');
      }
    } finally {
      setAccountsLoading(false);
    }
  }, [accounts.length]);

  // 初始加载
  useEffect(() => {
    if (!accountsLoadedRef.current) {
      fetchAccounts();
    }
  }, []);

  // refreshTrigger 变化时刷新（静默刷新）
  useEffect(() => {
    if (refreshTrigger > 0) {
      fetchAccounts(true);
    }
  }, [refreshTrigger]);

  // ========== SSE 实时日志连接 ==========
  useEffect(() => {
    const isProcessing = accounts.some(acc => acc.status === 'processing' || acc.status === 'pending');
    
    if (isProcessing && !eventSourceRef.current) {
      // 有账号正在同步，连接 SSE
      const apiBase = import.meta.env.VITE_API_BASE_URL || '';
      const sseUrl = `${apiBase}/api/sync-logs/stream`;
      
      console.log('%c[同步日志] 连接实时日志流...', 'color: #10B981; font-weight: bold;');
      
      const eventSource = new EventSource(sseUrl);
      eventSourceRef.current = eventSource;
      
      eventSource.onmessage = (event) => {
        try {
          const log = JSON.parse(event.data);
          
          // Handle cookie status events
          if (log.type === 'cookie_status') {
            console.log(`%c[Cookie状态] ${log.status}: ${log.message}`, 
              log.status === 'invalid' ? LOG_COLORS.error : LOG_COLORS.warn);
            
            // Update cookie status state
            setCookieStatus({
              status: log.status,
              message: log.message,
              extra: log.extra || {},
              timestamp: Date.now(),
            });
            
            // Dispatch global event for UserLogin component
            window.dispatchEvent(new CustomEvent(COOKIE_STATUS_EVENT, { 
              detail: { status: log.status, message: log.message, extra: log.extra }
            }));
            
            // If cookie is invalid, also dispatch the existing event
            if (log.status === COOKIE_STATUS.INVALID) {
              window.dispatchEvent(new CustomEvent('cookie-invalid'));
            }
            return;
          }
          
          const level = log.level || 'info';
          const style = LOG_COLORS[level] || LOG_COLORS.info;
          const prefix = level === 'error' ? '❌' : level === 'warn' ? '⚠️' : level === 'info' ? 'ℹ️' : '🔍';
          
          // 构建日志消息
          let msg = `${prefix} [${log.account_name || '系统'}] ${log.message}`;
          if (log.note_id) {
            msg += ` (笔记: ${log.note_id})`;
          }
          
          console.log(`%c[同步日志] ${msg}`, style);
          
          // 如果有额外信息，也输出
          if (log.extra && Object.keys(log.extra).length > 0) {
            console.log('  详情:', log.extra);
          }
        } catch (e) {
          // 忽略解析错误（如心跳包）
        }
      };
      
      eventSource.onerror = (error) => {
        console.log('%c[同步日志] 连接断开，将在下次同步时重连', 'color: #6B7280;');
        eventSource.close();
        eventSourceRef.current = null;
      };
    } else if (!isProcessing && eventSourceRef.current) {
      // 没有账号在同步，关闭 SSE 连接
      console.log('%c[同步日志] 同步完成，断开日志流', 'color: #10B981; font-weight: bold;');
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    
    // 清理函数
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, [accounts]);

  // 搜索用户
  const handleSearchUsers = useCallback(async (query) => {
    try {
      const result = await searchApi.searchUsers(query);
      return Array.isArray(result) ? result : [];
    } catch (error) {
      console.error("Search failed", error);
      return [];
    }
  }, []);

  // 添加用户
  const handleAddUser = useCallback(async (user) => {
    try {
      // 确保 user_id 有值
      const userId = user.id || user.user_id || user.red_id;
      if (!userId) {
        console.error("Missing user_id", user);
        alert('无法添加该用户：缺少用户ID');
        return false;
      }
      
      const payload = {
        name: user.name || user.red_id || userId,
        avatar: user.image || '',
        user_id: userId,
        red_id: user.red_id || '',
        xsec_token: user.xsec_token || '',  // 添加 xsec_token 用于同步数据
        desc: user.desc || '',
        fans: user.fans || '',
      };
      
      console.log("Adding user:", payload);
      await accountApi.add(payload);
      setRefreshTrigger(prev => prev + 1);
      return true;
    } catch (error) {
      console.error("Add user failed", error);
      // 如果是重复添加，提示用户
      if (error.status === 409) {
        alert('该博主已添加过了');
      } else {
        alert(`添加失败: ${error.message || '未知错误'}`);
      }
      return false;
    }
  }, []);

  // 触发刷新
  const triggerRefresh = useCallback(() => {
    setRefreshTrigger(prev => prev + 1);
  }, []);

  // 清除 Cookie 状态警告
  const dismissCookieStatus = useCallback(() => {
    setCookieStatus(null);
  }, []);

  // 自动清除限流警告（30秒后）
  useEffect(() => {
    if (cookieStatus?.status === COOKIE_STATUS.RATE_LIMITED) {
      const timer = setTimeout(() => {
        setCookieStatus(null);
      }, 30000);
      return () => clearTimeout(timer);
    }
  }, [cookieStatus]);

  // Cookie 状态警告组件
  const CookieStatusBanner = useMemo(() => {
    if (!cookieStatus) return null;
    
    const isInvalid = cookieStatus.status === COOKIE_STATUS.INVALID;
    const bgColor = isInvalid ? 'bg-red-50 border-red-200' : 'bg-orange-50 border-orange-200';
    const textColor = isInvalid ? 'text-red-700' : 'text-orange-700';
    const iconColor = isInvalid ? 'text-red-500' : 'text-orange-500';
    
    return (
      <div className={`fixed top-0 left-0 right-0 z-50 ${bgColor} border-b px-4 py-3 shadow-sm`}>
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <AlertTriangle className={`w-5 h-5 ${iconColor} flex-shrink-0`} />
            <div className="flex-1">
              <p className={`text-sm font-medium ${textColor}`}>
                {isInvalid ? 'Cookie 已失效' : '访问频次异常'}
              </p>
              <p className={`text-xs ${textColor} opacity-80`}>
                {cookieStatus.message}
                {cookieStatus.extra?.cooldown_seconds && (
                  <span className="ml-2 inline-flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    冷却 {cookieStatus.extra.cooldown_seconds} 秒
                  </span>
                )}
              </p>
            </div>
          </div>
          <button
            onClick={dismissCookieStatus}
            className={`p-1 rounded hover:bg-white/50 ${textColor}`}
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }, [cookieStatus, dismissCookieStatus]);

  return (
    <div className="flex h-screen w-full bg-gray-100 font-sans">
      {/* Cookie 状态警告横幅 */}
      {CookieStatusBanner}
      
      <Sidebar 
        onSearch={setSearchTerm}
        isSearchVisible={isSearchVisible}
        onSearchUsers={handleSearchUsers}
        onAddUser={handleAddUser}
        onCancelSearch={() => setIsSearchVisible(false)}
      />
      <main className="flex-1 flex flex-col overflow-hidden">
        <Routes>
          <Route 
            path="/accounts" 
            element={
              <>
                <div className="p-6 pb-0">
                  <h2 className="text-2xl font-bold text-gray-800">博主管理</h2>
                </div>
                <ContentArea 
                  searchTerm={searchTerm} 
                  onAddClick={() => setIsSearchVisible(true)}
                  refreshTrigger={refreshTrigger}
                  onRefresh={triggerRefresh}
                  accounts={accounts}
                  setAccounts={setAccounts}
                  loading={accountsLoading}
                  setLoading={setAccountsLoading}
                  error={accountsError}
                  setError={setAccountsError}
                  fetchAccounts={fetchAccounts}
                />
              </>
            } 
          />
          <Route 
            path="/download" 
            element={
              <>
                <div className="p-6 pb-0">
                  <h2 className="text-2xl font-bold text-gray-800">笔记下载</h2>
                </div>
                <DownloadPage accounts={accounts} accountsLoading={accountsLoading} />
              </>
            } 
          />
          <Route 
            path="/settings" 
            element={
              <>
                <div className="p-6 pb-0">
                  <h2 className="text-2xl font-bold text-gray-800">系统设置</h2>
                </div>
                <div className="flex-1 p-6 flex items-center justify-center text-gray-400">
                  Feature coming soon...
                </div>
              </>
            } 
          />
          {/* 默认重定向到 /accounts */}
          <Route path="/" element={<Navigate to="/accounts" replace />} />
          <Route path="*" element={<Navigate to="/accounts" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;

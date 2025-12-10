import React, { useState, useEffect, useCallback } from 'react';
import { User, LogIn, LogOut, KeyRound, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw } from 'lucide-react';
import { authApi, COOKIE_INVALID_EVENT } from '../services';

// 默认头像
const DEFAULT_AVATAR = "https://api.dicebear.com/7.x/avataaars/svg?seed=Felix";

// 轮询间隔（毫秒）- 30秒
const POLL_INTERVAL = 30000;

// 运行时长更新间隔（毫秒）- 1秒
const RUNTIME_UPDATE_INTERVAL = 1000;

/**
 * 格式化运行时长
 * @param {number} seconds - 秒数
 * @returns {string} 格式化后的时长字符串
 */
const formatDuration = (seconds) => {
  if (!seconds || seconds < 0) return '0秒';
  
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  
  const parts = [];
  if (days > 0) parts.push(`${days}天`);
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0) parts.push(`${minutes}分钟`);
  if (secs > 0 || parts.length === 0) parts.push(`${secs}秒`);
  
  return parts.join(' ');
};

/**
 * 格式化日期时间
 * @param {string} isoString - ISO 格式的日期字符串
 * @returns {string} 格式化后的日期时间
 */
const formatDateTime = (isoString) => {
  if (!isoString) return '未知';
  const date = new Date(isoString);
  return date.toLocaleString('zh-CN', {
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

export const UserLogin = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showManualInput, setShowManualInput] = useState(false);
  const [cookieInput, setCookieInput] = useState('');
  const [runInfo, setRunInfo] = useState(null);
  const [currentRunSeconds, setCurrentRunSeconds] = useState(0);
  const [invalidInfo, setInvalidInfo] = useState(null); // 失效信息

  // 获取当前用户信息
  const fetchUser = useCallback(async (forceCheck = false) => {
    try {
      const data = await authApi.getCurrentUser(forceCheck);
      
      if (data.is_connected) {
        setUser({
          userId: data.user_id,
          username: data.nickname || '小红书用户',
          avatar: data.avatar || DEFAULT_AVATAR
        });
        setError(null);
        setInvalidInfo(null);
        
        // 设置运行时长信息
        if (data.run_info) {
          setRunInfo(data.run_info);
          setCurrentRunSeconds(data.run_info.current_run_seconds || 0);
        }
      } else {
        setUser(null);
        
        // 如果之前是连接状态，显示失效信息
        if (data.was_connected) {
          setError('登录已失效，请重新登录');
          setInvalidInfo({
            userId: data.user_id,
            nickname: data.nickname,
            avatar: data.avatar,
            runInfo: data.run_info,
          });
        }
        
        // 保留运行时长信息用于显示
        if (data.run_info) {
          setRunInfo(data.run_info);
          setCurrentRunSeconds(data.run_info.last_valid_duration || 0);
        }
      }
    } catch (err) {
      console.error("Failed to fetch user info", err);
      setUser(null);
    }
  }, []);

  useEffect(() => {
    // 首次加载时获取用户信息（强制验证）
    fetchUser(true);
    
    // 定期检查登录状态（不强制验证，由后端按需验证）
    const interval = setInterval(() => fetchUser(false), POLL_INTERVAL);
    
    // 监听 Cookie 失效事件（由其他 API 调用失败触发）
    const handleCookieInvalid = () => {
      console.log('Cookie invalid event received');
      setUser(null);
      setError('登录已失效，请重新登录');
    };
    
    window.addEventListener(COOKIE_INVALID_EVENT, handleCookieInvalid);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener(COOKIE_INVALID_EVENT, handleCookieInvalid);
    };
  }, [fetchUser]);

  // 实时更新运行时长
  useEffect(() => {
    if (user && runInfo?.is_running) {
      const timer = setInterval(() => {
        setCurrentRunSeconds(prev => prev + 1);
      }, RUNTIME_UPDATE_INTERVAL);
      
      return () => clearInterval(timer);
    }
  }, [user, runInfo?.is_running]);

  // 系统登录
  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const result = await authApi.login();
      console.log("Login result:", result);
      
      // 重新获取用户信息
      await fetchUser();
      
      if (!user) {
        // 如果登录后还没有用户信息，提示手动添加
        setShowManualInput(true);
      }
    } catch (err) {
      console.error("Login failed", err);
      setError(err.message || "登录失败");
    } finally {
      setLoading(false);
    }
  };

  // 手动添加 Cookie（使用加密传输）
  const handleManualLogin = async () => {
    if (!cookieInput.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      // 使用加密传输
      const result = await authApi.setManualCookieEncrypted(cookieInput);
      
      if (result.user_id || result.nickname) {
        setUser({
          userId: result.user_id,
          username: result.nickname || '小红书用户',
          avatar: result.avatar || DEFAULT_AVATAR
        });
        
        // 设置运行时长信息
        if (result.run_info) {
          setRunInfo(result.run_info);
          setCurrentRunSeconds(0);
        }
        
        setShowManualInput(false);
        setCookieInput('');
        setInvalidInfo(null);
      }
    } catch (err) {
      // 如果加密传输失败，尝试明文传输
      console.warn("Encrypted cookie submission failed, trying plain:", err);
      try {
        const result = await authApi.setManualCookie(cookieInput);
        if (result.user_id || result.nickname) {
          setUser({
            userId: result.user_id,
            username: result.nickname || '小红书用户',
            avatar: result.avatar || DEFAULT_AVATAR
          });
          
          if (result.run_info) {
            setRunInfo(result.run_info);
            setCurrentRunSeconds(0);
          }
          
          setShowManualInput(false);
          setCookieInput('');
          setInvalidInfo(null);
        }
      } catch (err2) {
        setError(err2.message || "Cookie 验证失败");
      }
    } finally {
      setLoading(false);
    }
  };

  // 登出
  const handleLogout = async () => {
    try {
      await authApi.logout();
      setUser(null);
      setRunInfo(null);
      setCurrentRunSeconds(0);
    } catch (err) {
      console.error("Logout failed", err);
    }
  };

  // 运行时长显示组件
  const RunTimeDisplay = ({ isRunning }) => {
    if (!runInfo && currentRunSeconds === 0) return null;
    
    return (
      <div className="text-xs text-gray-500 mt-1 flex items-center gap-1">
        <Clock className="w-3 h-3" />
        {isRunning ? (
          <span className="text-green-600">
            运行中: {formatDuration(currentRunSeconds)}
          </span>
        ) : (
          <span className="text-orange-500">
            上次运行: {formatDuration(runInfo?.last_valid_duration || currentRunSeconds)}
          </span>
        )}
      </div>
    );
  };

  // 已登录状态
  if (user) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gray-200 overflow-hidden flex-shrink-0">
            {user.avatar ? (
              <img 
                src={user.avatar} 
                alt={user.username} 
                className="w-full h-full object-cover"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <User className="w-5 h-5 text-gray-400" />
              </div>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">
              {user.username}
            </p>
            <p className="text-xs text-green-500 flex items-center gap-1">
              <CheckCircle className="w-3 h-3" /> 已连接
            </p>
            <RunTimeDisplay isRunning={runInfo?.is_running} />
            {runInfo?.run_start_time && (
              <p className="text-xs text-gray-400 mt-0.5">
                开始于: {formatDateTime(runInfo.run_start_time)}
              </p>
            )}
          </div>
          <button 
            onClick={handleLogout}
            className="text-gray-400 hover:text-gray-600 p-1"
            title="断开连接"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    );
  }

  // 显示失效信息
  if (invalidInfo) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-3 p-2 bg-orange-50 rounded-md border border-orange-200">
          <div className="w-10 h-10 rounded-full bg-gray-200 overflow-hidden flex-shrink-0 opacity-50">
            {invalidInfo.avatar ? (
              <img 
                src={invalidInfo.avatar} 
                alt={invalidInfo.nickname} 
                className="w-full h-full object-cover grayscale"
              />
            ) : (
              <div className="w-full h-full flex items-center justify-center">
                <User className="w-5 h-5 text-gray-400" />
              </div>
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-600 truncate">
              {invalidInfo.nickname || '小红书用户'}
            </p>
            <p className="text-xs text-orange-500 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" /> Cookie 已失效
            </p>
            {invalidInfo.runInfo && (
              <p className="text-xs text-gray-500 mt-0.5 flex items-center gap-1">
                <Clock className="w-3 h-3" />
                上次运行: {formatDuration(invalidInfo.runInfo.last_valid_duration)}
              </p>
            )}
            {invalidInfo.runInfo?.invalidated_at && (
              <p className="text-xs text-gray-400 mt-0.5">
                失效于: {formatDateTime(invalidInfo.runInfo.invalidated_at)}
              </p>
            )}
          </div>
        </div>
        
        <button
          onClick={() => {
            setShowManualInput(true);
            setInvalidInfo(null);
          }}
          className="w-full flex items-center justify-center gap-2 text-orange-600 hover:text-orange-700 py-1 text-sm"
        >
          <RefreshCw className="w-3 h-3" />
          <span>重新登录</span>
        </button>
      </div>
    );
  }

  // 手动输入 Cookie
  if (showManualInput) {
    return (
      <div className="flex flex-col gap-2 p-2 bg-gray-50 rounded-md border border-gray-200">
        <div className="text-xs text-gray-600 mb-1">
          请粘贴小红书 Cookie：
        </div>
        <textarea
          value={cookieInput}
          onChange={(e) => setCookieInput(e.target.value)}
          placeholder="在此粘贴 Cookie 字符串..."
          className="w-full text-xs p-2 border rounded resize-none h-20 focus:outline-none focus:ring-1 focus:ring-red-500"
        />
        <div className="text-xs text-gray-400 flex items-center gap-1">
          <CheckCircle className="w-3 h-3 text-green-500" />
          Cookie 将加密传输
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleManualLogin}
            disabled={loading || !cookieInput.trim()}
            className="flex-1 bg-red-500 text-white text-xs py-1.5 rounded hover:bg-red-600 disabled:opacity-50"
          >
            {loading ? '验证中...' : '确认'}
          </button>
          <button
            onClick={() => {
              setShowManualInput(false);
              setError(null);
              setCookieInput('');
            }}
            className="flex-1 bg-gray-200 text-gray-700 text-xs py-1.5 rounded hover:bg-gray-300"
          >
            取消
          </button>
        </div>
        {error && (
          <p className="text-xs text-red-500 flex items-center gap-1">
            <XCircle className="w-3 h-3" /> {error}
          </p>
        )}
      </div>
    );
  }

  // 未登录状态
  return (
    <div className="flex flex-col gap-2">
      <button
        onClick={handleLogin}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors disabled:opacity-50"
      >
        {loading ? (
          <span className="text-sm">检查状态...</span>
        ) : (
          <>
            <LogIn className="w-4 h-4" />
            <span className="text-sm">系统登录</span>
          </>
        )}
      </button>
      
      <button
        onClick={() => setShowManualInput(true)}
        className="w-full flex items-center justify-center gap-2 text-gray-500 hover:text-gray-700 transition-colors py-1"
      >
        <KeyRound className="w-3 h-3" />
        <span className="text-xs">手动添加 Cookie</span>
      </button>

      {error && (
        <p className="text-xs text-red-500 text-center flex items-center justify-center gap-1">
          <XCircle className="w-3 h-3" /> {error}
        </p>
      )}
    </div>
  );
};

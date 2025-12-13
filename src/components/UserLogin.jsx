import React, { useState, useEffect, useCallback, useRef } from 'react';
import { User, LogIn, LogOut, KeyRound, CheckCircle, XCircle, Clock, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { authApi, COOKIE_INVALID_EVENT } from '../services';

// Cookie status changed event (from SSE sync logs)
const COOKIE_STATUS_EVENT = 'cookie-status-changed';

// 默认头像
const DEFAULT_AVATAR = "https://api.dicebear.com/7.x/avataaars/svg?seed=Felix";

// 轮询间隔（毫秒）- 30秒
const POLL_INTERVAL = 30000;

// 运行时长更新间隔（毫秒）- 1秒
const RUNTIME_UPDATE_INTERVAL = 1000;

// 本地缓存 key - 仅缓存用户基本信息用于快速展示，时间数据始终从服务端获取
const CACHE_KEY = 'xhs_user_cache';

/**
 * 保存用户状态到本地缓存
 * 注意：只缓存用户基本信息，不缓存时间数据（时间数据从服务端实时获取）
 */
const saveUserCache = (userData) => {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({
      user: userData.user,
      // 不再缓存 runInfo 和 currentRunSeconds，这些数据从服务端实时获取
      cachedAt: Date.now()
    }));
  } catch (e) {
    console.warn('Failed to save user cache:', e);
  }
};

/**
 * 从本地缓存读取用户状态
 * 仅用于快速展示用户头像和名称，避免页面闪烁
 * 时间数据始终从服务端获取
 */
const loadUserCache = () => {
  try {
    const cached = sessionStorage.getItem(CACHE_KEY);
    if (cached) {
      const data = JSON.parse(cached);
      // 缓存有效期 5 分钟（仅用于快速展示用户基本信息）
      if (Date.now() - data.cachedAt < 5 * 60 * 1000) {
        return {
          user: data.user,
          // 不返回缓存的时间数据，强制从服务端获取
          runInfo: null,
          currentRunSeconds: 0
        };
      }
    }
  } catch (e) {
    console.warn('Failed to load user cache:', e);
  }
  return null;
};

/**
 * 清除用户缓存
 */
const clearUserCache = () => {
  try {
    sessionStorage.removeItem(CACHE_KEY);
  } catch (e) {
    console.warn('Failed to clear user cache:', e);
  }
};

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
  // 从缓存初始化用户状态，避免页面跳转时闪烁
  const cachedUser = loadUserCache();
  const [user, setUser] = useState(cachedUser?.user || null);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(!cachedUser); // 初始化状态
  const [error, setError] = useState(null);
  const [showManualInput, setShowManualInput] = useState(false);
  const [cookieInput, setCookieInput] = useState('');
  const [runInfo, setRunInfo] = useState(cachedUser?.runInfo || null);
  const [currentRunSeconds, setCurrentRunSeconds] = useState(cachedUser?.currentRunSeconds || 0);
  const [invalidInfo, setInvalidInfo] = useState(null); // 失效信息
  const [rateLimitInfo, setRateLimitInfo] = useState(null); // 限流信息
  
  // 用于防止重复请求
  const fetchingRef = useRef(false);

  // 获取当前用户信息
  const fetchUser = useCallback(async (forceCheck = false) => {
    // 防止重复请求
    if (fetchingRef.current) return;
    fetchingRef.current = true;
    
    try {
      const data = await authApi.getCurrentUser(forceCheck);
      
      if (data.is_connected) {
        const newUser = {
          userId: data.user_id,
          username: data.nickname || '小红书用户',
          avatar: data.avatar || DEFAULT_AVATAR
        };
        setUser(newUser);
        setError(null);
        setInvalidInfo(null);
        
        // 设置运行时长信息 - 使用服务端返回的实时数据
        const newRunInfo = data.run_info || null;
        const newRunSeconds = data.run_info?.current_run_seconds || 0;
        setRunInfo(newRunInfo);
        setCurrentRunSeconds(newRunSeconds);
        
        // 保存到缓存（只缓存用户基本信息，不缓存时间数据）
        saveUserCache({ user: newUser });
      } else {
        setUser(null);
        clearUserCache(); // 清除缓存
        
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
      // 只有在没有缓存用户时才清除状态
      if (!cachedUser) {
        setUser(null);
      }
    } finally {
      fetchingRef.current = false;
      setInitializing(false);
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
      clearUserCache();
      setError('登录已失效，请重新登录');
    };
    
    // 监听 Cookie 状态变化事件（由 SSE 同步日志触发）
    const handleCookieStatusChanged = (event) => {
      const { status, message, extra } = event.detail || {};
      console.log('Cookie status changed:', status, message);
      
      if (status === 'invalid') {
        // Cookie 失效
        setUser(null);
        clearUserCache();
        setError('登录已失效，请重新登录');
        if (extra) {
          setInvalidInfo({
            userId: extra.user_id,
            nickname: extra.nickname,
            avatar: null,
            runInfo: extra.run_info,
          });
        }
      } else if (status === 'rate_limited') {
        // 限流警告 - 显示在用户信息下方
        setRateLimitInfo({
          message,
          count: extra?.rate_limit_count || 0,
          cooldown: extra?.cooldown_seconds || 0,
          timestamp: Date.now(),
        });
      }
    };
    
    window.addEventListener(COOKIE_INVALID_EVENT, handleCookieInvalid);
    window.addEventListener(COOKIE_STATUS_EVENT, handleCookieStatusChanged);
    
    return () => {
      clearInterval(interval);
      window.removeEventListener(COOKIE_INVALID_EVENT, handleCookieInvalid);
      window.removeEventListener(COOKIE_STATUS_EVENT, handleCookieStatusChanged);
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

  // 自动清除限流警告（冷却时间后）
  useEffect(() => {
    if (rateLimitInfo) {
      const timer = setTimeout(() => {
        setRateLimitInfo(null);
      }, (rateLimitInfo.cooldown || 30) * 1000);
      
      return () => clearTimeout(timer);
    }
  }, [rateLimitInfo]);

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
        const newUser = {
          userId: result.user_id,
          username: result.nickname || '小红书用户',
          avatar: result.avatar || DEFAULT_AVATAR
        };
        setUser(newUser);
        
        // 设置运行时长信息 - 使用服务端返回的数据（包含正确的起始时间）
        const newRunInfo = result.run_info || null;
        if (newRunInfo) {
          setRunInfo(newRunInfo);
          // 使用服务端返回的当前运行秒数，而不是固定为0
          setCurrentRunSeconds(newRunInfo.current_run_seconds || 0);
        } else {
          setRunInfo(null);
          setCurrentRunSeconds(0);
        }
        
        // 保存到缓存（只缓存用户信息）
        saveUserCache({ user: newUser });
        
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
          const newUser = {
            userId: result.user_id,
            username: result.nickname || '小红书用户',
            avatar: result.avatar || DEFAULT_AVATAR
          };
          setUser(newUser);
          
          // 设置运行时长信息 - 使用服务端返回的数据（包含正确的起始时间）
          const newRunInfo = result.run_info || null;
          if (newRunInfo) {
            setRunInfo(newRunInfo);
            // 使用服务端返回的当前运行秒数
            setCurrentRunSeconds(newRunInfo.current_run_seconds || 0);
          } else {
            setRunInfo(null);
            setCurrentRunSeconds(0);
          }
          
          // 保存到缓存（只缓存用户信息）
          saveUserCache({ user: newUser });
          
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
      clearUserCache(); // 清除缓存
    } catch (err) {
      console.error("Logout failed", err);
    }
  };

  // 运行时长显示组件
  const RunTimeDisplay = ({ isRunning }) => {
    if (!runInfo && currentRunSeconds === 0) return null;
    
    const statusClass = isRunning ? 'text-green-600' : 'text-orange-500';
    const label = isRunning ? '运行中' : '上次运行';
    const value = isRunning
      ? formatDuration(currentRunSeconds)
      : formatDuration(runInfo?.last_valid_duration || currentRunSeconds);
    
    return (
      <div className="flex items-center gap-1 text-xs text-gray-500 whitespace-nowrap">
        <Clock className="w-3 h-3" />
        <span className={statusClass}>
          {label}: {value}
        </span>
      </div>
    );
  };

  // 初始化加载状态（没有缓存时显示）
  if (initializing && !user) {
    return (
      <div className="flex items-center justify-center gap-2 py-3 text-gray-500">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">检查登录状态...</span>
      </div>
    );
  }

  // 已登录状态
  if (user) {
    return (
      <div className="flex flex-col gap-2">
        {/* 限流警告 */}
        {rateLimitInfo && (
          <div className="flex items-center gap-2 p-2 bg-orange-50 rounded-md border border-orange-200 text-xs">
            <AlertTriangle className="w-4 h-4 text-orange-500 flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <p className="text-orange-700 font-medium">访问频次异常</p>
              <p className="text-orange-600 truncate">
                累计 {rateLimitInfo.count} 次，冷却 {rateLimitInfo.cooldown}秒
              </p>
            </div>
          </div>
        )}
        
        <div className="flex items-start gap-3">
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
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {user.username}
                </p>
                <p className="mt-0.5 text-xs text-green-500 flex items-center gap-1">
                  <CheckCircle className="w-3 h-3" /> 已连接
                </p>
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
        </div>
        <div className="text-xs text-gray-500 space-y-0.5">
          <div className="min-h-[18px] flex items-center">
            <RunTimeDisplay isRunning={runInfo?.is_running} />
          </div>
          <div className="min-h-[18px] text-gray-400">
            {runInfo?.run_start_time && (
              <span>开始于: {formatDateTime(runInfo.run_start_time)}</span>
            )}
          </div>
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

import React, { useState, useEffect, useCallback } from 'react';
import { User, LogIn, LogOut, KeyRound, CheckCircle, XCircle } from 'lucide-react';
import { authApi, COOKIE_INVALID_EVENT } from '../services';

// 默认头像
const DEFAULT_AVATAR = "https://api.dicebear.com/7.x/avataaars/svg?seed=Felix";

// 轮询间隔（毫秒）- 2分钟
const POLL_INTERVAL = 120000;

export const UserLogin = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showManualInput, setShowManualInput] = useState(false);
  const [cookieInput, setCookieInput] = useState('');

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
      } else {
        setUser(null);
        // 如果之前是连接状态，显示提示
        if (data.was_connected) {
          setError('登录已失效，请重新登录');
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

  // 手动添加 Cookie
  const handleManualLogin = async () => {
    if (!cookieInput.trim()) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const result = await authApi.setManualCookie(cookieInput);
      
      if (result.success) {
        setUser({
          userId: result.data.user_id,
          username: result.data.nickname || '小红书用户',
          avatar: result.data.avatar || DEFAULT_AVATAR
        });
        setShowManualInput(false);
        setCookieInput('');
      }
    } catch (err) {
      setError(err.message || "Cookie 验证失败");
    } finally {
      setLoading(false);
    }
  };

  // 登出
  const handleLogout = async () => {
    try {
      await authApi.logout();
      setUser(null);
    } catch (err) {
      console.error("Logout failed", err);
    }
  };

  // 已登录状态
  if (user) {
    return (
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
        </div>
        <button 
          onClick={handleLogout}
          className="text-gray-400 hover:text-gray-600 p-1"
          title="断开连接"
        >
          <LogOut className="w-4 h-4" />
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

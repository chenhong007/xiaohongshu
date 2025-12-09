import React, { useState, useEffect } from 'react';
import { User, LogIn, LogOut, KeyRound } from 'lucide-react';

export const UserLogin = () => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showManualInput, setShowManualInput] = useState(false);
  const [cookieInput, setCookieInput] = useState('');

  const fetchUser = async () => {
    try {
      // Use relative path to leverage Vite proxy
      const response = await fetch('/api/user/me');
      if (response.ok) {
        const data = await response.json();
        if (data.is_connected) {
          setUser({
            username: data.nickname,
            avatar: data.avatar || "https://api.dicebear.com/7.x/avataaars/svg?seed=Felix"
          });
        }
      }
    } catch (err) {
      console.error("Failed to fetch user info", err);
    }
  };

  useEffect(() => {
    fetchUser();
    // 可以设置轮询或者其他机制来检查登录状态更新
    const interval = setInterval(fetchUser, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      // 调用后端触发登录脚本
      const response = await fetch('/api/login', {
        method: 'POST',
      });
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "登录请求失败");
      }

      const result = await response.json();
      console.log("Login script output:", result);
      
      // 重新获取用户信息
      await fetchUser();
      
    } catch (error) {
      console.error("Login check failed", error);
      setError(error.message || "连接失败");
    } finally {
      setLoading(false);
    }
  };

  const handleManualLogin = async () => {
      if (!cookieInput.trim()) return;
      setLoading(true);
      setError(null);
      try {
        const response = await fetch('/api/cookie/manual', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ cookies: cookieInput })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || "Cookie 验证失败");
        }
        
        await fetchUser();
        setShowManualInput(false);
        setCookieInput('');
      } catch (err) {
         setError(err.message);
      } finally {
         setLoading(false);
      }
  };

  if (user) {
    return (
      <div className="flex items-center gap-3">
        <img 
          src={user.avatar} 
          alt={user.username} 
          className="w-10 h-10 rounded-full bg-gray-200 object-cover"
        />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">
            {user.username}
          </p>
          <p className="text-xs text-green-500">
            已连接
          </p>
        </div>
        <button 
          onClick={() => {
            // 这里只是清除前端状态，实际后端 cookie 还在
             setUser(null);
          }}
          className="text-gray-400 hover:text-gray-600"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    );
  }

  if (showManualInput) {
      return (
        <div className="flex flex-col gap-2 p-2 bg-gray-50 rounded-md border border-gray-200">
            <textarea
                value={cookieInput}
                onChange={(e) => setCookieInput(e.target.value)}
                placeholder="在此粘贴 Cookie..."
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
                    }}
                    className="flex-1 bg-gray-200 text-gray-700 text-xs py-1.5 rounded hover:bg-gray-300"
                >
                    取消
                </button>
            </div>
             {error && <p className="text-xs text-red-500 text-center">{error}</p>}
        </div>
      );
  }

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
        className="w-full flex items-center justify-center gap-2 text-gray-500 hover:text-gray-700 transition-colors"
      >
         <KeyRound className="w-3 h-3" />
         <span className="text-xs">手动添加 Cookie</span>
      </button>

      {error && <p className="text-xs text-red-500 text-center">{error}</p>}
    </div>
  );
};

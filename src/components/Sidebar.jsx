import React, { useState, useEffect, useCallback } from 'react';
import { NavLink } from 'react-router-dom';
import { LayoutDashboard, Download, Settings, Users, Search, X, CheckCircle } from 'lucide-react';
import { UserLogin } from './UserLogin';

export const Sidebar = ({ 
  onSearch, 
  isSearchVisible, 
  onSearchUsers, 
  onAddUser, 
  onCancelSearch 
}) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);
  const [addedUsers, setAddedUsers] = useState(new Set());

  const menuItems = [
    { id: 'accounts', path: '/accounts', label: '博主管理', icon: Users },
    { id: 'download', path: '/download', label: '笔记下载', icon: Download },
    { id: 'settings', path: '/settings', label: '设置', icon: Settings },
  ];

  // 搜索用户（防抖）
  useEffect(() => {
    if (!isSearchVisible) {
      setQuery('');
      setResults([]);
      setAddedUsers(new Set());
      return;
    }

    const timer = setTimeout(async () => {
      if (query.trim() && onSearchUsers) {
        setIsSearching(true);
        try {
          const users = await onSearchUsers(query);
          setResults(users || []);
        } catch (err) {
          console.error('Search failed:', err);
          setResults([]);
        } finally {
          setIsSearching(false);
        }
      } else {
        setResults([]);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [query, isSearchVisible, onSearchUsers]);

  // 添加用户
  const handleAddUser = useCallback(async (user) => {
    const success = await onAddUser(user);
    if (success) {
      setAddedUsers(prev => new Set([...prev, user.id]));
    }
  }, [onAddUser]);

  // 关闭搜索
  const handleClose = useCallback(() => {
    setQuery('');
    setResults([]);
    setAddedUsers(new Set());
    onCancelSearch();
  }, [onCancelSearch]);

  return (
    <div className="w-64 bg-white border-r h-screen flex flex-col">
      {/* Logo */}
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold text-red-500 flex items-center gap-2">
          <span className="text-2xl">📕</span> 小红书采集系统
        </h1>
      </div>

      <div className="p-4 flex-1 overflow-hidden flex flex-col">
        {/* 搜索模式 */}
        {isSearchVisible && (
          <div className="flex flex-col h-full">
            {/* 搜索框 */}
            <div className="relative mb-3">
              <Search className="absolute left-3 top-3 text-gray-400 w-4 h-4" />
              <input
                type="text"
                placeholder="搜索博主名称..." 
                className="w-full pl-9 pr-8 py-2 border rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                autoFocus
              />
              <button 
                onClick={handleClose}
                className="absolute right-2 top-2 p-1 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            {/* 搜索结果 */}
            <div className="flex-1 overflow-y-auto border rounded-md bg-gray-50">
              {isSearching && (
                <div className="p-4 text-center text-gray-500 text-sm">
                  搜索中...
                </div>
              )}
              
              {!isSearching && results.length === 0 && query.trim() && (
                <div className="p-4 text-center text-gray-400 text-sm">
                  未找到相关博主
                </div>
              )}
              
              {!isSearching && results.length === 0 && !query.trim() && (
                <div className="p-4 text-center text-gray-400 text-sm">
                  输入关键词搜索博主
                </div>
              )}
              
              {!isSearching && results.map((user, idx) => {
                const isAdded = addedUsers.has(user.id);
                return (
                  <div 
                    key={user.id || idx} 
                    className={`flex items-center gap-2 p-3 border-b last:border-b-0 ${
                      isAdded ? 'bg-green-50' : 'hover:bg-white cursor-pointer'
                    }`}
                    onClick={() => !isAdded && handleAddUser(user)}
                  >
                    {/* 头像 */}
                    <div className="w-10 h-10 rounded-full bg-gray-200 overflow-hidden flex-shrink-0">
                      {user.image ? (
                        <img src={user.image} className="w-full h-full object-cover" alt={user.name} />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-xs text-gray-500">无图</div>
                      )}
                    </div>
                    
                    {/* 信息 */}
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium truncate flex items-center gap-1">
                        {user.name || user.red_id || user.id}
                        {user.is_verified && (
                          <span className="text-xs text-yellow-500">✓</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-400 truncate">
                        {user.red_id && <span>小红书号: {user.red_id}</span>}
                        {user.fans && <span className="ml-2">粉丝: {user.fans}</span>}
                      </div>
                    </div>
                    
                    {/* 添加状态 */}
                    {isAdded ? (
                      <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0" />
                    ) : (
                      <span className="text-xs text-blue-500 flex-shrink-0">+添加</span>
                    )}
                  </div>
                );
              })}
            </div>
            
            {/* 完成按钮 */}
            <button
              onClick={handleClose}
              className="mt-3 w-full py-2 bg-gray-100 text-gray-600 rounded-md text-sm hover:bg-gray-200"
            >
              完成
            </button>
          </div>
        )}

        {/* 普通菜单 */}
        {!isSearchVisible && (
          <nav className="space-y-1">
            {menuItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.id}
                  to={item.path}
                  className={({ isActive }) =>
                    `w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                      isActive
                        ? 'bg-red-50 text-red-600'
                        : 'text-gray-600 hover:bg-gray-50'
                    }`
                  }
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </NavLink>
              );
            })}
          </nav>
        )}
      </div>

      {/* 用户登录区域 */}
      <div className="mt-auto p-4 border-t">
        <UserLogin />
      </div>
    </div>
  );
};

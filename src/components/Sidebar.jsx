import React, { useState, useEffect } from 'react';
import { LayoutDashboard, Download, Settings, Users, Search, X } from 'lucide-react';
import { UserLogin } from './UserLogin';

export const Sidebar = ({ activeTab, setActiveTab, onSearch, isSearchVisible, onSearchUsers, onAddUser, onCancelSearch }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isSearching, setIsSearching] = useState(false);

  const menuItems = [
    { id: 'accounts', label: '账号管理', icon: Users },
    { id: 'download', label: '笔记下载', icon: Download },
    { id: 'settings', label: '设置', icon: Settings },
  ];

  useEffect(() => {
    if (!isSearchVisible) {
        setQuery('');
        setResults([]);
        return;
    }

    const timer = setTimeout(async () => {
      if (query.trim() && onSearchUsers) {
        setIsSearching(true);
        const users = await onSearchUsers(query);
        setResults(users);
        setIsSearching(false);
      } else {
          setResults([]);
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [query, isSearchVisible, onSearchUsers]);

  return (
    <div className="w-64 bg-white border-r h-screen flex flex-col">
      <div className="p-4 border-b">
        <h1 className="text-xl font-bold text-red-500 flex items-center gap-2">
          小红书采集系统
        </h1>
      </div>

      <div className="p-4">
        {/* Search Box in Sidebar as per requirement */}
        {isSearchVisible && (
            <div className="relative mb-6">
                <Search className="absolute left-3 top-3 transform text-gray-400 w-4 h-4" />
                <input
                  type="text"
                  placeholder="搜索博主名称..." 
                  className="w-full pl-9 pr-8 py-2 border rounded-md text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
                <button 
                    onClick={() => {
                        setQuery('');
                        onCancelSearch();
                    }}
                    className="absolute right-2 top-2 p-1 text-gray-400 hover:text-gray-600 rounded-full hover:bg-gray-100"
                >
                    <X className="w-4 h-4" />
                </button>
                 {(results.length > 0 || isSearching) && (
                    <div className="absolute top-full left-0 right-0 bg-white border rounded-md shadow-lg mt-1 max-h-60 overflow-y-auto z-50">
                        {isSearching && <div className="p-2 text-center text-gray-500 text-xs">搜索中...</div>}
                        {!isSearching && results.map((user, idx) => (
                            <div 
                                key={user.id || idx} 
                                className="flex items-center gap-2 p-2 hover:bg-gray-50 cursor-pointer border-b last:border-b-0"
                                onClick={() => {
                                    onAddUser(user);
                                    setResults([]); 
                                    setQuery('');
                                }}
                            >
                                <div className="w-10 h-10 rounded-full bg-gray-200 overflow-hidden flex-shrink-0">
                                    {user.image ? <img src={user.image} className="w-full h-full object-cover" alt={user.name} /> : <div className="w-full h-full flex items-center justify-center text-xs text-gray-500">无图</div>}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-sm font-medium truncate">{user.name}</div>
                                    <div className="text-xs text-gray-400 truncate">
                                        ID: {user.red_id || user.id}
                                        {user.fans && <span className="ml-2">粉丝: {user.fans}</span>}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        )}

        {!isSearchVisible && (
        <nav className="space-y-1">
          {menuItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.id}
                onClick={() => setActiveTab(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                  activeTab === item.id
                    ? 'bg-red-50 text-red-600'
                    : 'text-gray-600 hover:bg-gray-50'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </button>
            );
          })}
        </nav>
        )}
      </div>

      <div className="mt-auto p-4 border-t">
        <UserLogin />
      </div>
    </div>
  );
};


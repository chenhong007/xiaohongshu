import React, { useState, useCallback } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Sidebar } from './components/Sidebar';
import { ContentArea } from './components/ContentArea';
import { DownloadPage } from './components/DownloadPage';
import { searchApi, accountApi } from './services';

function App() {
  const [searchTerm, setSearchTerm] = useState('');
  const [isSearchVisible, setIsSearchVisible] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

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

  return (
    <div className="flex h-screen w-full bg-gray-100 font-sans">
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
                <DownloadPage />
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

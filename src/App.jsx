import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { ContentArea } from './components/ContentArea';
import { DownloadPage } from './components/DownloadPage';

function App() {
  const [activeTab, setActiveTab] = useState('accounts');
  const [searchTerm, setSearchTerm] = useState('');
  const [isSearchVisible, setIsSearchVisible] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleSearchUsers = async (query) => {
    try {
      const res = await fetch(`/api/search/users?keyword=${encodeURIComponent(query)}`);
      if (res.ok) {
        return await res.json();
      }
    } catch (error) {
      console.error("Search failed", error);
    }
    return [];
  };

  const handleAddUser = async (user) => {
    try {
      const payload = {
        name: user.name,
        avatar: user.image,
        user_id: user.id || user.red_id, // Prefer ID but fallback if needed, though ID is usually what we want for API
      };
      
      const res = await fetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        setRefreshTrigger(prev => prev + 1);
        // Optional: Keep search visible to add more, or close it. 
        // User requirement: "User clicks confirm... display in right side... sync to sql"
        // It doesn't explicitly say close, but refreshing the list is key.
      }
    } catch (error) {
      console.error("Add user failed", error);
    }
  };

  return (
    <div className="flex h-screen w-full bg-gray-100 font-sans">
      <Sidebar 
        activeTab={activeTab} 
        setActiveTab={setActiveTab} 
        onSearch={setSearchTerm}
        isSearchVisible={isSearchVisible}
        onSearchUsers={handleSearchUsers}
        onAddUser={handleAddUser}
        onCancelSearch={() => setIsSearchVisible(false)}
      />
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar could be here, but requirement says Left Side for Navigation, Right Side for content. 
            Search is in Sidebar as per instruction 'Left side shows search box'.
        */}
        <div className="p-6 pb-0">
            <h2 className="text-2xl font-bold text-gray-800">
                {activeTab === 'accounts' && '博主管理'}
                {activeTab === 'download' && '笔记下载'}
                {activeTab === 'settings' && '系统设置'}
            </h2>
        </div>
        
        {activeTab === 'accounts' && (
             <ContentArea 
                activeTab={activeTab} 
                searchTerm={searchTerm} 
                onAddClick={() => setIsSearchVisible(true)}
                refreshTrigger={refreshTrigger}
             />
        )}
        {activeTab === 'download' && (
             <DownloadPage />
        )}
        {activeTab === 'settings' && (
            <div className="flex-1 p-6 flex items-center justify-center text-gray-400">
                Feature coming soon...
            </div>
        )}
      </main>
    </div>
  );
}

export default App;


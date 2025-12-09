import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Search, RefreshCw, ChevronDown, Coffee, Download as DownloadIcon, Play, Image, Video, ExternalLink, Trash2, X, Check, Calendar } from 'lucide-react';
import { noteApi, accountApi } from '../services';

export const DownloadPage = () => {
  // 数据状态
  const [notes, setNotes] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [dataLoaded, setDataLoaded] = useState(false); // 标记是否已加载过数据
  
  // 筛选条件
  const [selectedUserIds, setSelectedUserIds] = useState([]);
  const [timeRange, setTimeRange] = useState('all');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [keyword, setKeyword] = useState('');
  const [matchMode, setMatchMode] = useState('and');
  const [noteType, setNoteType] = useState('all');
  
  // 数值过滤条件（最小值）
  const [likedCountMin, setLikedCountMin] = useState('');
  const [collectedCountMin, setCollectedCountMin] = useState('');
  const [commentCountMin, setCommentCountMin] = useState('');
  
  // 博主选择下拉框状态
  const [bloggerDropdownOpen, setBloggerDropdownOpen] = useState(false);
  const [bloggerSearchText, setBloggerSearchText] = useState('');
  const bloggerDropdownRef = useRef(null);
  
  // 分页和排序
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [sortBy, setSortBy] = useState('upload_time');
  const [sortOrder, setSortOrder] = useState('desc');
  
  // 选中状态
  const [selectedNoteIds, setSelectedNoteIds] = useState(new Set());

  // 获取账号列表（用于筛选下拉框）
  useEffect(() => {
    const fetchAccounts = async () => {
      try {
        const data = await accountApi.getAll();
        setAccounts(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error('Failed to fetch accounts:', err);
      }
    };
    fetchAccounts();
  }, []);

  // 点击外部关闭博主下拉框
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (bloggerDropdownRef.current && !bloggerDropdownRef.current.contains(event.target)) {
        setBloggerDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // 过滤博主列表
  const filteredAccounts = accounts.filter(acc => {
    if (!bloggerSearchText.trim()) return true;
    const searchLower = bloggerSearchText.toLowerCase();
    return (acc.name || '').toLowerCase().includes(searchLower) || 
           (acc.user_id || '').toLowerCase().includes(searchLower);
  });

  // 获取笔记列表
  const fetchNotes = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        page,
        page_size: pageSize,
        sort_by: sortBy,
        sort_order: sortOrder,
        note_type: noteType,
      };
      
      // 时间范围处理
      if (timeRange === 'custom') {
        if (customStartDate) params.start_date = customStartDate;
        if (customEndDate) params.end_date = customEndDate;
      } else if (timeRange !== 'all') {
        params.time_range = timeRange;
      }
      
      if (selectedUserIds.length > 0) {
        params.user_ids = selectedUserIds.join(',');
      }
      
      if (keyword.trim()) {
        params.keyword = keyword.trim();
        params.match_mode = matchMode;
      }
      
      // 数值过滤参数（最小值）
      if (likedCountMin !== '') params.liked_count_min = parseInt(likedCountMin);
      if (collectedCountMin !== '') params.collected_count_min = parseInt(collectedCountMin);
      if (commentCountMin !== '') params.comment_count_min = parseInt(commentCountMin);
      
      const result = await noteApi.getAll(params);
      
      if (result.success) {
        setNotes(result.data.items || []);
        setTotalCount(result.data.total || 0);
        setDataLoaded(true);
      }
    } catch (err) {
      console.error('Failed to fetch notes:', err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, sortBy, sortOrder, selectedUserIds, timeRange, customStartDate, customEndDate, keyword, matchMode, noteType, likedCountMin, collectedCountMin, commentCountMin]);

  // 页码、排序变化时自动加载（仅在已加载过数据的情况下）
  useEffect(() => {
    if (dataLoaded) {
      fetchNotes();
    }
  }, [page, sortBy, sortOrder, fetchNotes, dataLoaded]);

  // 刷新数据 - 重置到第一页
  const handleRefresh = () => {
    if (page === 1) {
      // 如果已经在第一页，直接请求
      setDataLoaded(true);
      fetchNotes();
    } else {
      // 否则先重置页码，useEffect 会自动触发请求
      setDataLoaded(true);
      setPage(1);
    }
  };

  // 博主选择相关处理
  const toggleBloggerSelect = (userId) => {
    setSelectedUserIds(prev => {
      if (prev.includes(userId)) {
        return prev.filter(id => id !== userId);
      } else {
        return [...prev, userId];
      }
    });
  };

  const selectAllBloggers = () => {
    setSelectedUserIds([]);
  };

  const getSelectedBloggersText = () => {
    if (selectedUserIds.length === 0) return '全部博主';
    if (selectedUserIds.length === 1) {
      const acc = accounts.find(a => a.user_id === selectedUserIds[0]);
      return acc?.name || acc?.user_id || '1位博主';
    }
    return `已选择 ${selectedUserIds.length} 位博主`;
  };

  // 切换排序
  const handleSort = (field) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(field);
      setSortOrder('desc');
    }
  };

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedNoteIds.size === notes.length && notes.length > 0) {
      setSelectedNoteIds(new Set());
    } else {
      setSelectedNoteIds(new Set(notes.map(n => n.note_id)));
    }
  };

  // 切换选择
  const toggleSelect = (noteId) => {
    const newSelected = new Set(selectedNoteIds);
    if (newSelected.has(noteId)) {
      newSelected.delete(noteId);
    } else {
      newSelected.add(noteId);
    }
    setSelectedNoteIds(newSelected);
  };

  // 导出笔记数据
  const handleExport = async (format = 'json') => {
    const noteIds = selectedNoteIds.size > 0 ? Array.from(selectedNoteIds) : [];
    
    try {
      const result = await noteApi.export(noteIds, format);
      
      if (result.success) {
        const json = JSON.stringify(result.data, null, 2);
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `notes_${new Date().toISOString().slice(0, 10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
      }
    } catch (err) {
      console.error('Export failed:', err);
      alert('导出失败');
    }
  };

  // 删除选中笔记
  const handleDelete = async () => {
    if (selectedNoteIds.size === 0) {
      alert('请先选择要删除的笔记');
      return;
    }
    
    if (!confirm(`确定要删除选中的 ${selectedNoteIds.size} 条笔记吗？`)) return;
    
    try {
      await noteApi.batchDelete(Array.from(selectedNoteIds));
      setSelectedNoteIds(new Set());
      fetchNotes();
    } catch (err) {
      console.error('Delete failed:', err);
      alert('删除失败');
    }
  };

  // 计算总页数
  const totalPages = Math.ceil(totalCount / pageSize);

  // 排序图标
  const SortIcon = ({ field }) => (
    <ChevronDown 
      className={`w-3 h-3 inline ml-1 transition-transform ${
        sortBy === field ? (sortOrder === 'asc' ? 'rotate-180' : '') : 'opacity-50'
      }`} 
    />
  );

  return (
    <div className="flex-1 bg-gray-50 p-6 overflow-auto flex flex-col">
      {/* 筛选条件 */}
      <div className="bg-white p-4 rounded-lg shadow-sm border mb-4 space-y-4">
        {/* 第一行筛选 */}
        <div className="flex gap-4 items-start">
          {/* 博主选择下拉框 */}
          <div className="w-64 relative" ref={bloggerDropdownRef}>
            <label className="block text-xs text-gray-500 mb-1">博主选择</label>
            <div 
              className="w-full border rounded-md px-3 py-2 text-sm bg-white text-gray-900 cursor-pointer flex items-center justify-between hover:border-gray-400"
              onClick={() => setBloggerDropdownOpen(!bloggerDropdownOpen)}
            >
              <span className={selectedUserIds.length === 0 ? 'text-gray-500' : ''}>
                {getSelectedBloggersText()}
              </span>
              <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${bloggerDropdownOpen ? 'rotate-180' : ''}`} />
            </div>
            
            {/* 下拉菜单 */}
            {bloggerDropdownOpen && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border rounded-md shadow-lg z-50 max-h-72 overflow-hidden flex flex-col">
                {/* 搜索框 */}
                <div className="p-2 border-b">
                  <div className="relative">
                    <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input 
                      type="text"
                      placeholder="搜索博主..."
                      value={bloggerSearchText}
                      onChange={(e) => setBloggerSearchText(e.target.value)}
                      className="w-full border rounded px-8 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
                      onClick={(e) => e.stopPropagation()}
                    />
                    {bloggerSearchText && (
                      <X 
                        className="absolute right-2 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 cursor-pointer hover:text-gray-600"
                        onClick={(e) => { e.stopPropagation(); setBloggerSearchText(''); }}
                      />
                    )}
                  </div>
                </div>
                
                {/* 全部博主选项 */}
                <div 
                  className={`px-3 py-2 cursor-pointer flex items-center gap-2 hover:bg-gray-50 border-b ${selectedUserIds.length === 0 ? 'bg-red-50 text-red-600' : ''}`}
                  onClick={(e) => { e.stopPropagation(); selectAllBloggers(); }}
                >
                  <div className={`w-4 h-4 border rounded flex items-center justify-center ${selectedUserIds.length === 0 ? 'bg-red-500 border-red-500' : 'border-gray-300'}`}>
                    {selectedUserIds.length === 0 && <Check className="w-3 h-3 text-white" />}
                  </div>
                  <span className="text-sm font-medium">全部博主</span>
                </div>
                
                {/* 博主列表 */}
                <div className="overflow-y-auto flex-1">
                  {filteredAccounts.length === 0 ? (
                    <div className="px-3 py-4 text-center text-gray-400 text-sm">
                      {bloggerSearchText ? '未找到匹配的博主' : '暂无博主数据'}
                    </div>
                  ) : (
                    filteredAccounts.map(acc => (
                      <div 
                        key={acc.id}
                        className={`px-3 py-2 cursor-pointer flex items-center gap-2 hover:bg-gray-50 ${selectedUserIds.includes(acc.user_id) ? 'bg-red-50' : ''}`}
                        onClick={(e) => { e.stopPropagation(); toggleBloggerSelect(acc.user_id); }}
                      >
                        <div className={`w-4 h-4 border rounded flex items-center justify-center ${selectedUserIds.includes(acc.user_id) ? 'bg-red-500 border-red-500' : 'border-gray-300'}`}>
                          {selectedUserIds.includes(acc.user_id) && <Check className="w-3 h-3 text-white" />}
                        </div>
                        <div className="w-6 h-6 rounded-full bg-gray-200 overflow-hidden flex-shrink-0">
                          {acc.avatar && <img src={acc.avatar} alt="" className="w-full h-full object-cover" />}
                        </div>
                        <span className="text-sm truncate">{acc.name || acc.user_id}</span>
                      </div>
                    ))
                  )}
                </div>
                
                {/* 已选中提示 */}
                {selectedUserIds.length > 0 && (
                  <div className="px-3 py-2 border-t bg-gray-50 flex items-center justify-between">
                    <span className="text-xs text-gray-500">已选择 {selectedUserIds.length} 位博主</span>
                    <button 
                      className="text-xs text-red-500 hover:text-red-600"
                      onClick={(e) => { e.stopPropagation(); selectAllBloggers(); }}
                    >
                      清除选择
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
          
          {/* 时间范围 */}
          <div className="w-40">
            <label className="block text-xs text-gray-500 mb-1">时间范围</label>
            <div className="relative">
              <select 
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm appearance-none bg-white text-gray-900"
              >
                <option value="all">全部时间</option>
                <option value="day">最近1天</option>
                <option value="week">最近1周</option>
                <option value="month">最近1月</option>
                <option value="custom">自定义时间</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>
          
          {/* 自定义时间范围 */}
          {timeRange === 'custom' && (
            <>
              <div className="w-40">
                <label className="block text-xs text-gray-500 mb-1">开始日期</label>
                <div className="relative">
                  <input 
                    type="date"
                    value={customStartDate}
                    onChange={(e) => setCustomStartDate(e.target.value)}
                    className="w-full border rounded-md px-3 py-2 text-sm bg-white text-gray-900"
                  />
                </div>
              </div>
              <div className="w-40">
                <label className="block text-xs text-gray-500 mb-1">结束日期</label>
                <div className="relative">
                  <input 
                    type="date"
                    value={customEndDate}
                    onChange={(e) => setCustomEndDate(e.target.value)}
                    className="w-full border rounded-md px-3 py-2 text-sm bg-white text-gray-900"
                  />
                </div>
              </div>
            </>
          )}
          
          <div className="w-36">
            <label className="block text-xs text-gray-500 mb-1">笔记类型</label>
            <div className="relative">
              <select 
                value={noteType}
                onChange={(e) => setNoteType(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm appearance-none bg-white text-gray-900"
              >
                <option value="all">全部类型</option>
                <option value="图集">图集</option>
                <option value="视频">视频</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>
        </div>

        {/* 第二行筛选 */}
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">标题搜索 (多个关键词用空格分隔)</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input 
                type="text" 
                placeholder="输入标题关键词"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
                className="w-full border rounded-md pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
              />
            </div>
          </div>
          
          <div className="w-48">
            <label className="block text-xs text-gray-500 mb-1">匹配模式</label>
            <div className="relative">
              <select 
                value={matchMode}
                onChange={(e) => setMatchMode(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm appearance-none bg-white text-gray-900"
              >
                <option value="and">AND (所有关键词)</option>
                <option value="or">OR (任意关键词)</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>
        </div>
        
        {/* 第三行筛选 - 数值过滤 */}
        <div className="flex gap-4 items-end flex-wrap">
          {/* 点赞数过滤 */}
          <div className="w-28">
            <label className="block text-xs text-gray-500 mb-1">点赞数 ≥</label>
            <input 
              type="number"
              min="0"
              placeholder="最小值"
              value={likedCountMin}
              onChange={(e) => setLikedCountMin(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
              className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          
          {/* 收藏数过滤 */}
          <div className="w-28">
            <label className="block text-xs text-gray-500 mb-1">收藏数 ≥</label>
            <input 
              type="number"
              min="0"
              placeholder="最小值"
              value={collectedCountMin}
              onChange={(e) => setCollectedCountMin(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
              className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          
          {/* 评论数过滤 */}
          <div className="w-28">
            <label className="block text-xs text-gray-500 mb-1">评论数 ≥</label>
            <input 
              type="number"
              min="0"
              placeholder="最小值"
              value={commentCountMin}
              onChange={(e) => setCommentCountMin(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
              className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
            />
          </div>
          
          <button 
            onClick={handleRefresh}
            disabled={loading}
            className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 text-sm flex items-center gap-1 h-[38px] disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> 刷新数据
          </button>
        </div>
      </div>

      {/* 操作工具栏 */}
      <div className="mb-4 flex gap-2 items-center">
        <button 
          onClick={() => handleExport('json')}
          className="px-4 py-1.5 bg-white border rounded text-gray-600 text-sm flex items-center gap-2 hover:bg-gray-50"
        >
          <DownloadIcon className="w-3 h-3" /> 
          导出 {selectedNoteIds.size > 0 ? `(${selectedNoteIds.size})` : '全部'}
        </button>
        
        <button 
          onClick={handleDelete}
          disabled={selectedNoteIds.size === 0}
          className="px-4 py-1.5 bg-white border rounded text-red-600 text-sm flex items-center gap-2 hover:bg-red-50 disabled:opacity-50"
        >
          <Trash2 className="w-3 h-3" /> 删除选中
        </button>
        
        <div className="ml-auto text-sm text-gray-500">
          共 {totalCount} 条笔记
        </div>
      </div>

      {/* 表格 */}
      <div className="bg-white rounded-lg shadow-sm border flex-1 flex flex-col min-h-[400px]">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-gray-500 bg-gray-50 border-b">
              <tr>
                <th className="p-4 w-10">
                  <input 
                    type="checkbox" 
                    checked={selectedNoteIds.size === notes.length && notes.length > 0}
                    onChange={toggleSelectAll}
                    className="rounded border-gray-300 text-blue-600"
                  />
                </th>
                <th className="p-4">类型</th>
                <th 
                  className="p-4 cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('upload_time')}
                >
                  发布时间 <SortIcon field="upload_time" />
                </th>
                <th className="p-4">博主</th>
                <th className="p-4 min-w-[200px]">标题</th>
                <th 
                  className="p-4 cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('liked_count')}
                >
                  点赞 <SortIcon field="liked_count" />
                </th>
                <th 
                  className="p-4 cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('collected_count')}
                >
                  收藏 <SortIcon field="collected_count" />
                </th>
                <th 
                  className="p-4 cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('comment_count')}
                >
                  评论 <SortIcon field="comment_count" />
                </th>
                <th className="p-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {notes.length === 0 ? (
                <tr>
                  <td colSpan="9" className="p-0">
                    <div className="flex flex-col items-center justify-center text-gray-400 py-16">
                      <Coffee className="w-12 h-12 mb-4 text-gray-300" />
                      <p>
                        {loading ? '加载中...' : 
                          dataLoaded ? '暂无数据，请先同步博主笔记' : 
                          '请设置筛选条件后点击"刷新数据"按钮加载数据'}
                      </p>
                      {!dataLoaded && !loading && (
                        <button 
                          onClick={handleRefresh}
                          className="mt-4 px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 text-sm flex items-center gap-1"
                        >
                          <RefreshCw className="w-4 h-4" /> 刷新数据
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                notes.map((note) => (
                  <tr key={note.note_id} className="border-b hover:bg-gray-50">
                    <td className="p-4">
                      <input 
                        type="checkbox" 
                        checked={selectedNoteIds.has(note.note_id)}
                        onChange={() => toggleSelect(note.note_id)}
                        className="rounded border-gray-300 text-blue-600"
                      />
                    </td>
                    <td className="p-4">
                      {note.type === '视频' ? (
                        <span className="inline-flex items-center gap-1 text-blue-600">
                          <Video className="w-4 h-4" /> 视频
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-green-600">
                          <Image className="w-4 h-4" /> 图集
                        </span>
                      )}
                    </td>
                    <td className="p-4 text-gray-500">{note.upload_time || '-'}</td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-full bg-gray-200 overflow-hidden flex-shrink-0">
                          {note.avatar && <img src={note.avatar} alt="" className="w-full h-full object-cover" />}
                        </div>
                        <span className="truncate max-w-[100px]">{note.nickname}</span>
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="truncate max-w-[200px]" title={note.title}>
                        {note.title || '无标题'}
                      </div>
                    </td>
                    <td className="p-4 text-center">{note.liked_count || 0}</td>
                    <td className="p-4 text-center">{note.collected_count || 0}</td>
                    <td className="p-4 text-center">{note.comment_count || 0}</td>
                    <td className="p-4">
                      <a 
                        href={`https://www.xiaohongshu.com/explore/${note.note_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-500 hover:text-blue-700"
                        title="查看原文"
                      >
                        <ExternalLink className="w-4 h-4" />
                      </a>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {/* 分页 */}
        {totalPages > 1 && (
          <div className="p-4 border-t flex items-center justify-between">
            <div className="text-sm text-gray-500">
              第 {page} / {totalPages} 页，共 {totalCount} 条
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-50"
              >
                上一页
              </button>
              <button
                onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                disabled={page === totalPages}
                className="px-3 py-1 border rounded text-sm disabled:opacity-50 hover:bg-gray-50"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

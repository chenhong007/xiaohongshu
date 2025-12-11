import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Search, RefreshCw, ChevronDown, Coffee, Download as DownloadIcon, Play, Image, Video, ExternalLink, Trash2, X, Check, Calendar, Heart, Star, MessageCircle, RotateCcw, Share2, Copy, CheckCircle } from 'lucide-react';
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
  const [shareCountMin, setShareCountMin] = useState('');
  
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
  
  // 复制状态
  const [copiedNoteId, setCopiedNoteId] = useState(null);
  const [copiedAll, setCopiedAll] = useState(false);

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
      if (shareCountMin !== '') params.share_count_min = parseInt(shareCountMin);
      
      const result = await noteApi.getAll(params);
      
      // api.js 已经自动解包了 data 字段，所以 result 直接是 { items, total, ... }
      if (result && result.items !== undefined) {
        setNotes(result.items || []);
        setTotalCount(result.total || 0);
        setDataLoaded(true);
      }
    } catch (err) {
      console.error('Failed to fetch notes:', err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, sortBy, sortOrder, selectedUserIds, timeRange, customStartDate, customEndDate, keyword, matchMode, noteType, likedCountMin, collectedCountMin, commentCountMin, shareCountMin]);

  // 页码、排序变化时自动加载（仅在已加载过数据的情况下）
  useEffect(() => {
    if (dataLoaded) {
      fetchNotes();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, sortBy, sortOrder]);

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

  // 重置筛选条件
  const handleReset = () => {
    setSelectedUserIds([]);
    setTimeRange('all');
    setCustomStartDate('');
    setCustomEndDate('');
    setKeyword('');
    setMatchMode('and');
    setNoteType('all');
    setLikedCountMin('');
    setCollectedCountMin('');
    setCommentCountMin('');
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
    if (selectedUserIds.length === 0) return `全部博主 (${accounts.length})`;
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

  // 复制单行内容
  const copyContent = async (noteId, content) => {
    try {
      await navigator.clipboard.writeText(content || '');
      setCopiedNoteId(noteId);
      setTimeout(() => setCopiedNoteId(null), 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  // 复制全部内容详情
  const copyAllContents = async () => {
    try {
      const allContents = notes
        .map(note => note.desc || '')
        .filter(desc => desc.trim())
        .join('\n\n---\n\n');
      await navigator.clipboard.writeText(allContents);
      setCopiedAll(true);
      setTimeout(() => setCopiedAll(false), 2000);
    } catch (err) {
      console.error('Copy all failed:', err);
    }
  };

  // 构建筛选条件参数
  const buildFilterParams = () => {
    const params = {
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
    if (shareCountMin !== '') params.share_count_min = parseInt(shareCountMin);
    
    return params;
  };

  // 导出笔记数据
  const handleExport = async (format = 'json') => {
    const noteIds = selectedNoteIds.size > 0 ? Array.from(selectedNoteIds) : [];
    
    try {
      // 如果没有选中特定笔记，则传递当前筛选条件
      const filterParams = noteIds.length === 0 ? buildFilterParams() : {};
      const result = await noteApi.export(noteIds, format, filterParams);
      
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
      {/* 筛选条件 - 新版紧凑设计 */}
      <div className="bg-white p-5 rounded-lg shadow-sm border mb-4">
        <div className="flex flex-col gap-4">
          {/* 第一行：主要筛选条件 */}
          <div className="flex flex-wrap items-center gap-3">
            {/* 博主选择 */}
            <div className="w-56 relative z-20" ref={bloggerDropdownRef}>
              <div 
                className="w-full border rounded-md px-3 py-2 text-sm bg-white text-gray-900 cursor-pointer flex items-center justify-between hover:border-red-400 transition-colors"
                onClick={() => setBloggerDropdownOpen(!bloggerDropdownOpen)}
              >
                <span className={`truncate ${selectedUserIds.length === 0 ? 'text-gray-500' : 'text-gray-900'}`}>
                  {getSelectedBloggersText()}
                </span>
                <ChevronDown className={`w-4 h-4 text-gray-400 transition-transform ${bloggerDropdownOpen ? 'rotate-180' : ''}`} />
              </div>
              
              {/* 下拉菜单 */}
              {bloggerDropdownOpen && (
                <div className="absolute top-full left-0 right-0 mt-1 bg-white border rounded-md shadow-lg z-50 max-h-72 overflow-hidden flex flex-col">
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
                  
                  <div 
                    className={`px-3 py-2 cursor-pointer flex items-center gap-2 hover:bg-gray-50 border-b ${selectedUserIds.length === 0 ? 'bg-red-50 text-red-600' : ''}`}
                    onClick={(e) => { e.stopPropagation(); selectAllBloggers(); }}
                  >
                    <div className={`w-4 h-4 border rounded flex items-center justify-center ${selectedUserIds.length === 0 ? 'bg-red-500 border-red-500' : 'border-gray-300'}`}>
                      {selectedUserIds.length === 0 && <Check className="w-3 h-3 text-white" />}
                    </div>
                    <span className="text-sm font-medium">全部博主 ({accounts.length})</span>
                  </div>
                  
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
                </div>
              )}
            </div>

            {/* 笔记类型 */}
            <div className="w-32">
              <select 
                value={noteType}
                onChange={(e) => setNoteType(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-red-500 hover:border-red-400 transition-colors"
              >
                <option value="all">全部类型</option>
                <option value="图集">图集</option>
                <option value="视频">视频</option>
              </select>
            </div>

            {/* 时间范围 */}
            <div className="w-36">
              <select 
                value={timeRange}
                onChange={(e) => setTimeRange(e.target.value)}
                className="w-full border rounded-md px-3 py-2 text-sm bg-white text-gray-900 focus:outline-none focus:ring-1 focus:ring-red-500 hover:border-red-400 transition-colors"
              >
                <option value="all">全部时间</option>
                <option value="day">最近1天</option>
                <option value="week">最近1周</option>
                <option value="month">最近1月</option>
                <option value="custom">自定义...</option>
              </select>
            </div>

            {/* 关键词搜索 + 匹配模式 */}
            <div className="flex-1 min-w-[280px] flex shadow-sm rounded-md">
              <div className="relative flex-1">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-4 w-4 text-gray-400" />
                </div>
                <input 
                  type="text" 
                  placeholder="标题/内容关键词..."
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
                  className="w-full border border-r-0 rounded-l-md pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-red-500 hover:border-red-400 transition-colors z-10 relative"
                />
              </div>
              <select 
                value={matchMode}
                onChange={(e) => setMatchMode(e.target.value)}
                className="border rounded-r-md px-3 py-2 text-sm bg-gray-50 text-gray-600 focus:outline-none focus:ring-1 focus:ring-red-500 border-l-gray-200 hover:bg-gray-100 transition-colors"
                title="关键词匹配模式"
              >
                <option value="and">AND</option>
                <option value="or">OR</option>
              </select>
            </div>
          </div>

          {/* 第二行：数据指标 & 操作 */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-t pt-4 border-dashed border-gray-100">
            <div className="flex flex-wrap items-center gap-3">
              {/* 自定义时间选择器 (仅当选中自定义时显示) */}
              {timeRange === 'custom' && (
                <div className="flex items-center gap-2 bg-gray-50 px-3 py-1.5 rounded-md border text-sm mr-2 animate-in fade-in slide-in-from-left-2 duration-200">
                  <Calendar className="w-3.5 h-3.5 text-gray-500" />
                  <input 
                    type="date"
                    value={customStartDate}
                    onChange={(e) => setCustomStartDate(e.target.value)}
                    className="bg-transparent border-none p-0 text-gray-700 focus:ring-0 text-sm w-28"
                  />
                  <span className="text-gray-400">-</span>
                  <input 
                    type="date"
                    value={customEndDate}
                    onChange={(e) => setCustomEndDate(e.target.value)}
                    className="bg-transparent border-none p-0 text-gray-700 focus:ring-0 text-sm w-28"
                  />
                </div>
              )}

              {/* 数据指标 */}
              <div className="flex items-center gap-2">
                <div className="relative group">
                  <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none">
                    <Heart className="h-3.5 w-3.5 text-gray-400 group-hover:text-red-400 transition-colors" />
                  </div>
                  <input 
                    type="number"
                    min="0"
                    placeholder="点赞 ≥"
                    value={likedCountMin}
                    onChange={(e) => setLikedCountMin(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
                    className="pl-8 w-24 border rounded-md py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-red-500 hover:border-red-400 transition-colors"
                  />
                </div>
                <div className="relative group">
                  <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none">
                    <Star className="h-3.5 w-3.5 text-gray-400 group-hover:text-yellow-400 transition-colors" />
                  </div>
                  <input 
                    type="number"
                    min="0"
                    placeholder="收藏 ≥"
                    value={collectedCountMin}
                    onChange={(e) => setCollectedCountMin(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
                    className="pl-8 w-24 border rounded-md py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-red-500 hover:border-red-400 transition-colors"
                  />
                </div>
                <div className="relative group">
                  <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none">
                    <MessageCircle className="h-3.5 w-3.5 text-gray-400 group-hover:text-blue-400 transition-colors" />
                  </div>
                  <input 
                    type="number"
                    min="0"
                    placeholder="评论 ≥"
                    value={commentCountMin}
                    onChange={(e) => setCommentCountMin(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleRefresh()}
                    className="pl-8 w-24 border rounded-md py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-red-500 hover:border-red-400 transition-colors"
                  />
                </div>
              </div>
            </div>

            {/* 操作按钮 */}
            <div className="flex items-center gap-3 ml-auto">
              <button 
                onClick={handleReset}
                className="text-gray-500 hover:text-gray-700 text-sm px-2 py-1.5 flex items-center gap-1 hover:bg-gray-100 rounded transition-colors"
                title="重置所有筛选条件"
              >
                <RotateCcw className="w-3.5 h-3.5" /> 重置
              </button>
              <button 
                onClick={handleRefresh}
                disabled={loading}
                className="px-5 py-2 bg-red-500 text-white rounded-md hover:bg-red-600 text-sm flex items-center gap-1.5 shadow-sm transition-all hover:shadow disabled:opacity-70 disabled:cursor-not-allowed"
              >
                {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                查询笔记
              </button>
            </div>
          </div>
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
                <th className="p-4">预览</th>
                <th className="p-4">远程URL</th>
                <th 
                  className="p-4 cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('upload_time')}
                >
                  发布时间 <SortIcon field="upload_time" />
                </th>
                <th className="p-4">博主</th>
                <th className="p-4 min-w-[200px]">标题</th>
                <th className="p-4 min-w-[300px]">
                  <div className="flex items-center gap-2">
                    <span>内容详情</span>
                    {notes.length > 0 && (
                      <button
                        onClick={copyAllContents}
                        className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded bg-gray-100 hover:bg-gray-200 text-gray-600 transition-colors"
                        title="复制全部内容"
                      >
                        {copiedAll ? <CheckCircle className="w-3 h-3 text-green-500" /> : <Copy className="w-3 h-3" />}
                        {copiedAll ? '已复制' : '全部复制'}
                      </button>
                    )}
                  </div>
                </th>
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
                <th 
                  className="p-4 cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('share_count')}
                >
                  转发 <SortIcon field="share_count" />
                </th>
                <th className="p-4">操作</th>
              </tr>
            </thead>
            <tbody>
              {notes.length === 0 ? (
                <tr>
                  <td colSpan="13" className="p-0">
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
                notes.map((note) => {
                  const previewSrc = note.cover_local || note.cover_remote || (note.image_list && note.image_list[0]);
                  const remoteSrc = note.cover_remote || (note.image_list && note.image_list[0]) || '';
                  return (
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
                    <td className="p-4">
                      {previewSrc ? (
                        <div className="group relative inline-block">
                          <img
                            src={previewSrc}
                            alt="封面"
                            className="w-12 h-12 rounded object-cover border border-gray-200"
                          />
                          <div className="hidden group-hover:block absolute left-14 top-1/2 -translate-y-1/2 z-50 bg-white border border-gray-200 rounded shadow-lg p-2">
                            <img
                              src={previewSrc}
                              alt="预览大图"
                              className="w-64 h-64 object-contain rounded"
                            />
                          </div>
                        </div>
                      ) : (
                        <span className="text-gray-400 text-xs">无图</span>
                      )}
                    </td>
                    <td className="p-4">
                      {remoteSrc ? (
                        <a 
                          href={remoteSrc} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          className="text-blue-500 hover:text-blue-700 break-all text-xs"
                          title={remoteSrc}
                        >
                          远程链接
                        </a>
                      ) : (
                        <span className="text-gray-400 text-xs">-</span>
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
                    <td className="p-4">
                      <div className="flex items-start gap-2">
                        <div 
                          className="truncate max-w-[280px] text-gray-600 text-xs leading-relaxed" 
                          title={note.desc || ''}
                        >
                          {note.desc ? (
                            note.desc.length > 100 ? note.desc.slice(0, 100) + '...' : note.desc
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </div>
                        {note.desc && (
                          <button
                            onClick={() => copyContent(note.note_id, note.desc)}
                            className="flex-shrink-0 p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
                            title="复制内容"
                          >
                            {copiedNoteId === note.note_id ? (
                              <CheckCircle className="w-3.5 h-3.5 text-green-500" />
                            ) : (
                              <Copy className="w-3.5 h-3.5" />
                            )}
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="p-4 text-center">{note.liked_count || 0}</td>
                    <td className="p-4 text-center">{note.collected_count || 0}</td>
                    <td className="p-4 text-center">{note.comment_count || 0}</td>
                    <td className="p-4 text-center">{note.share_count || 0}</td>
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
                  );
                })
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

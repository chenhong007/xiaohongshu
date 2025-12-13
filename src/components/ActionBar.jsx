import React from 'react';
import { 
  Upload, 
  Download, 
  Trash2, 
  Zap, 
  Database, 
  StopCircle,
  Wifi,
  WifiOff 
} from 'lucide-react';

/**
 * Action Bar Component
 * 
 * Provides action buttons for account management:
 * - Add account
 * - Import/Export
 * - Delete
 * - Sync controls (fast/deep)
 * - WebSocket status indicator
 */
export const ActionBar = ({
  onAddClick,
  onImport,
  onExport,
  onDelete,
  onBatchSync,
  onStopSync,
  onReset,
  selectedCount,
  isProcessing,
  isStopping,
  loading,
  wsConnected
}) => {
  return (
    <div className="p-4 border-b flex flex-wrap gap-3 items-center">
      {/* Add Button */}
      <button 
        onClick={onAddClick}
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 text-sm flex items-center gap-2"
      >
        <span>+ 添加</span>
      </button>
      
      <div className="h-6 w-px bg-gray-300 mx-1" />
      
      {/* Import/Export */}
      <button 
        onClick={onImport}
        className="px-3 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
      >
        <Upload className="w-3 h-3" /> 导入
      </button>
      
      <button 
        onClick={onExport}
        className="px-3 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
      >
        <Download className="w-3 h-3" /> 导出
      </button>
      
      {/* Delete */}
      <button 
        onClick={onDelete}
        className="px-3 py-2 bg-red-50 text-red-600 rounded hover:bg-red-100 text-sm flex items-center gap-1"
        disabled={selectedCount === 0}
      >
        <Trash2 className="w-3 h-3" /> 删除
      </button>
      
      <div className="h-6 w-px bg-gray-300 mx-1" />
      
      {/* Sync Controls */}
      {isProcessing ? (
        <button 
          onClick={onStopSync}
          disabled={isStopping}
          className={`px-4 py-2 text-white rounded text-sm flex items-center gap-2 ${
            isStopping 
              ? 'bg-gray-400 cursor-not-allowed' 
              : 'bg-red-500 hover:bg-red-600 animate-pulse'
          }`}
        >
          {isStopping ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Stopping...
            </>
          ) : (
            <>
              <StopCircle className="w-4 h-4" /> Stop Sync
            </>
          )}
        </button>
      ) : (
        <>
          <button 
            onClick={() => onBatchSync('fast')}
            className="px-4 py-2 bg-green-100 text-green-700 rounded hover:bg-green-200 text-sm flex items-center gap-1 border border-green-200"
            disabled={loading}
            title="快速同步 - 仅更新点赞数等"
          >
            <Zap className="w-4 h-4" /> 
            {selectedCount > 0 ? `快速同步 (${selectedCount})` : '快速同步全部'}
          </button>
          
          <button 
            onClick={() => onBatchSync('deep')}
            className="px-4 py-2 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 text-sm flex items-center gap-1 border border-blue-200"
            disabled={loading}
            title="深度同步 - 获取所有详情"
          >
            <Database className="w-4 h-4" /> 
            {selectedCount > 0 ? `深度同步 (${selectedCount})` : '深度同步全部'}
          </button>
        </>
      )}
      
      {/* WebSocket Status */}
      <div 
        className={`ml-auto flex items-center gap-1 px-2 py-1 rounded text-xs ${
          wsConnected ? 'bg-green-50 text-green-600' : 'bg-gray-50 text-gray-400'
        }`}
        title={wsConnected ? 'WebSocket 已连接' : '使用轮询模式'}
      >
        {wsConnected ? (
          <><Wifi className="w-3 h-3" /><span>实时</span></>
        ) : (
          <><WifiOff className="w-3 h-3" /><span>轮询</span></>
        )}
      </div>

      {/* Reset Button */}
      <button 
        onClick={onReset} 
        className="px-3 py-2 text-gray-400 hover:text-red-500 rounded text-sm flex items-center gap-1"
        title="清除所有数据"
      >
        <Trash2 className="w-3 h-3" /> 清除
      </button>
    </div>
  );
};

export default ActionBar;

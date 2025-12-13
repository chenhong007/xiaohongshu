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
        <span>+ Add</span>
      </button>
      
      <div className="h-6 w-px bg-gray-300 mx-1" />
      
      {/* Import/Export */}
      <button 
        onClick={onImport}
        className="px-3 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
      >
        <Upload className="w-3 h-3" /> Import
      </button>
      
      <button 
        onClick={onExport}
        className="px-3 py-2 bg-gray-100 text-gray-600 rounded hover:bg-gray-200 text-sm flex items-center gap-1"
      >
        <Download className="w-3 h-3" /> Export
      </button>
      
      {/* Delete */}
      <button 
        onClick={onDelete}
        className="px-3 py-2 bg-red-50 text-red-600 rounded hover:bg-red-100 text-sm flex items-center gap-1"
        disabled={selectedCount === 0}
      >
        <Trash2 className="w-3 h-3" /> Delete
      </button>
      
      <div className="h-6 w-px bg-gray-300 mx-1" />
      
      {/* Sync Controls */}
      {isProcessing ? (
        <button 
          onClick={onStopSync}
          className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600 text-sm flex items-center gap-2 animate-pulse"
        >
          <StopCircle className="w-4 h-4" /> Stop Sync
        </button>
      ) : (
        <>
          <button 
            onClick={() => onBatchSync('fast')}
            className="px-4 py-2 bg-green-100 text-green-700 rounded hover:bg-green-200 text-sm flex items-center gap-1 border border-green-200"
            disabled={loading}
            title="Quick sync - only updates like counts"
          >
            <Zap className="w-4 h-4" /> 
            {selectedCount > 0 ? `Fast Sync (${selectedCount})` : 'Fast Sync All'}
          </button>
          
          <button 
            onClick={() => onBatchSync('deep')}
            className="px-4 py-2 bg-blue-100 text-blue-700 rounded hover:bg-blue-200 text-sm flex items-center gap-1 border border-blue-200"
            disabled={loading}
            title="Deep sync - fetches all details"
          >
            <Database className="w-4 h-4" /> 
            {selectedCount > 0 ? `Deep Sync (${selectedCount})` : 'Deep Sync All'}
          </button>
        </>
      )}
      
      {/* WebSocket Status */}
      <div 
        className={`ml-auto flex items-center gap-1 px-2 py-1 rounded text-xs ${
          wsConnected ? 'bg-green-50 text-green-600' : 'bg-gray-50 text-gray-400'
        }`}
        title={wsConnected ? 'WebSocket connected' : 'Using polling mode'}
      >
        {wsConnected ? (
          <><Wifi className="w-3 h-3" /><span>Live</span></>
        ) : (
          <><WifiOff className="w-3 h-3" /><span>Polling</span></>
        )}
      </div>

      {/* Reset Button */}
      <button 
        onClick={onReset} 
        className="px-3 py-2 text-gray-400 hover:text-red-500 rounded text-sm flex items-center gap-1"
        title="Clear all data"
      >
        <Trash2 className="w-3 h-3" /> Clear
      </button>
    </div>
  );
};

export default ActionBar;

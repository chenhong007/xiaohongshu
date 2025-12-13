import React, { useState } from 'react';
import { 
  X, 
  Clock, 
  Ban, 
  AlertTriangle, 
  AlertCircle, 
  Key, 
  Image as ImageIcon, 
  CheckCircle,
  ChevronDown,
  ChevronUp,
  FileText
} from 'lucide-react';

const ISSUE_TYPE_CONFIG = {
  rate_limited: { icon: Clock, color: 'text-orange-500', bgColor: 'bg-orange-50', label: '频率限制' },
  unavailable: { icon: Ban, color: 'text-gray-500', bgColor: 'bg-gray-50', label: '不可用' },
  missing_field: { icon: AlertTriangle, color: 'text-yellow-600', bgColor: 'bg-yellow-50', label: '字段缺失' },
  fetch_failed: { icon: AlertCircle, color: 'text-red-500', bgColor: 'bg-red-50', label: '获取失败' },
  token_refresh: { icon: Key, color: 'text-blue-500', bgColor: 'bg-blue-50', label: '令牌刷新' },
  media_failed: { icon: ImageIcon, color: 'text-purple-500', bgColor: 'bg-purple-50', label: '媒体失败' },
  auth_error: { icon: AlertCircle, color: 'text-red-600', bgColor: 'bg-red-100', label: '认证错误' },
};

const getTimeStats = (logs) => {
  if (!logs?.start_time || !logs?.end_time) return null;
  const start = new Date(logs.start_time);
  const end = new Date(logs.end_time);
  const totalMs = end - start;
  const totalSeconds = Math.floor(totalMs / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  const summary = logs.summary || {};
  const processedCount = (summary.success || 0) + (summary.skipped || 0) + 
                         (summary.missing_field || 0) + (summary.fetch_failed || 0) +
                         (summary.unavailable || 0);
  const avgMs = processedCount > 0 ? totalMs / processedCount : 0;
  const avgSeconds = avgMs / 1000;
  return {
    startTime: start.toLocaleString(),
    endTime: end.toLocaleString(),
    totalFormatted: minutes > 0 ? `${minutes}分${seconds}秒` : `${seconds}秒`,
    avgFormatted: avgSeconds >= 1 ? `${avgSeconds.toFixed(1)}秒/笔记` : `${avgMs.toFixed(0)}毫秒/笔记`,
  };
};

const getIssueConfig = (type) => ISSUE_TYPE_CONFIG[type] || { icon: AlertCircle, color: 'text-gray-500', bgColor: 'bg-gray-50', label: type };

const SummaryCards = ({ summary }) => (
  <div className="grid grid-cols-4 gap-3">
    <div className="bg-blue-50 rounded-lg p-3 text-center">
      <div className="text-2xl font-bold text-blue-600">{summary.total || 0}</div>
      <div className="text-xs text-blue-600">总数</div>
    </div>
    <div className="bg-green-50 rounded-lg p-3 text-center">
      <div className="text-2xl font-bold text-green-600">{summary.success || 0}</div>
      <div className="text-xs text-green-600">成功</div>
    </div>
    <div className="bg-gray-50 rounded-lg p-3 text-center">
      <div className="text-2xl font-bold text-gray-600">{summary.skipped || 0}</div>
      <div className="text-xs text-gray-600">跳过</div>
    </div>
    <div className="bg-yellow-50 rounded-lg p-3 text-center">
      <div className="text-2xl font-bold text-yellow-600">
        {(summary.rate_limited || 0) + (summary.missing_field || 0) + (summary.fetch_failed || 0)}
      </div>
      <div className="text-xs text-yellow-600">问题</div>
    </div>
  </div>
);

const IssueItem = ({ issue }) => {
  const config = getIssueConfig(issue.type);
  const IconComponent = config.icon;
  return (
    <div className={`${config.bgColor} rounded-lg p-3 text-sm`}>
      <div className="flex items-start gap-2">
        <IconComponent className={`w-4 h-4 ${config.color} mt-0.5 flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`font-medium ${config.color}`}>{config.label}</span>
            {issue.note_id && (
              <a href={`https://www.xiaohongshu.com/explore/${issue.note_id}`} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-500 hover:underline">
                笔记: {issue.note_id.slice(0, 8)}...
              </a>
            )}
            <span className="text-xs text-gray-400">{issue.time && new Date(issue.time).toLocaleTimeString()}</span>
          </div>
          {issue.message && <p className="text-gray-600 text-xs mt-1 break-all">{issue.message}</p>}
          {issue.fields && <p className="text-xs text-gray-500 mt-1">缺失字段: {issue.fields.join(', ')}</p>}
        </div>
      </div>
    </div>
  );
};

export const SyncLogModal = ({ isOpen, onClose, account }) => {
  const [expandedIssues, setExpandedIssues] = useState(false);
  
  if (!isOpen || !account) return null;
  const logs = account.sync_logs;
  
  if (!logs) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50" onClick={onClose}>
        <div className="bg-white rounded-lg shadow-xl p-6 max-w-md" onClick={e => e.stopPropagation()}>
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-lg font-semibold">同步日志</h3>
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600"><X className="w-5 h-5" /></button>
          </div>
          <p className="text-gray-500 text-center py-8">暂无同步日志</p>
        </div>
      </div>
    );
  }
  
  const summary = logs.summary || {};
  const issues = logs.issues || [];
  const timeStats = getTimeStats(logs);
  const displayIssues = expandedIssues ? issues : issues.slice(0, 10);
  
  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex justify-between items-center p-4 border-b bg-gray-50">
          <div>
            <h3 className="text-lg font-semibold flex items-center gap-2">
              <FileText className="w-5 h-5 text-blue-500" />
              同步日志 - {account.name || account.user_id}
            </h3>
            {timeStats && (
              <div className="text-xs text-gray-600 mt-1 space-y-1">
                <p className="flex items-center gap-3">
                  <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded">开始: {timeStats.startTime}</span>
                  <span className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded">结束: {timeStats.endTime}</span>
                </p>
                <p className="flex items-center gap-3">
                  <span className="bg-blue-50 text-blue-600 px-2 py-0.5 rounded">总时长: {timeStats.totalFormatted}</span>
                  <span className="bg-green-50 text-green-600 px-2 py-0.5 rounded">平均: {timeStats.avgFormatted}</span>
                </p>
              </div>
            )}
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1"><X className="w-5 h-5" /></button>
        </div>
        
        <div className="p-4 border-b">
          <h4 className="text-sm font-medium text-gray-700 mb-3">统计摘要</h4>
          <SummaryCards summary={summary} />
        </div>
        
        <div className="flex-1 overflow-y-auto p-4">
          <div className="flex justify-between items-center mb-3">
            <h4 className="text-sm font-medium text-gray-700">问题列表 ({issues.length})</h4>
            {issues.length > 5 && (
              <button onClick={() => setExpandedIssues(!expandedIssues)} className="text-xs text-blue-500 hover:text-blue-700 flex items-center gap-1">
                {expandedIssues ? <><ChevronUp className="w-3 h-3" /> 收起</> : <><ChevronDown className="w-3 h-3" /> 展开</>}
              </button>
            )}
          </div>
          {issues.length === 0 ? (
            <div className="text-center py-8 text-gray-400">
              <CheckCircle className="w-12 h-12 mx-auto mb-2 text-green-400" />
              <p>无问题</p>
            </div>
          ) : (
            <div className="space-y-2">
              {displayIssues.map((issue, idx) => <IssueItem key={idx} issue={issue} />)}
              {!expandedIssues && issues.length > 10 && (
                <div className="text-center py-2">
                  <button onClick={() => setExpandedIssues(true)} className="text-sm text-blue-500 hover:text-blue-700">
                    还有 {issues.length - 10} 条...
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
        
        <div className="p-4 border-t bg-gray-50 flex justify-end">
          <button onClick={onClose} className="px-4 py-2 bg-gray-200 text-gray-700 rounded hover:bg-gray-300 text-sm">关闭</button>
        </div>
      </div>
    </div>
  );
};

export default SyncLogModal;

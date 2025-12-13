import React from 'react';
import { 
  RefreshCw, 
  CheckCircle, 
  Circle, 
  AlertCircle, 
  Zap, 
  Database, 
  Wrench,
  FileText,
  AlertTriangle
} from 'lucide-react';

/**
 * Account Table Row Component
 */
const AccountRow = ({ 
  account, 
  index, 
  isSelected, 
  onToggleSelect, 
  onSync, 
  onFixMissing, 
  onShowLog 
}) => {
  const hasIssues = account.sync_logs?.summary && (
    (account.sync_logs.summary.rate_limited || 0) + 
    (account.sync_logs.summary.missing_field || 0) + 
    (account.sync_logs.summary.fetch_failed || 0)
  ) > 0;

  return (
    <tr className="border-b hover:bg-gray-50">
      <td className="p-4">
        <input 
          type="checkbox" 
          checked={isSelected} 
          onChange={onToggleSelect}
          className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
        />
      </td>
      <td className="p-4 text-gray-500">{index + 1}</td>
      <td className="p-4">
        <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500 overflow-hidden">
          {account.avatar ? (
            <img src={account.avatar} alt={account.name} className="w-full h-full object-cover" />
          ) : (
            'IMG'
          )}
        </div>
      </td>
      <td className="p-4 font-medium">{account.name || account.user_id}</td>
      <td className="p-4">{account.fans !== undefined ? account.fans : '-'}</td>
      <td className="p-4 text-gray-500">
        {account.last_sync ? new Date(account.last_sync).toLocaleString() : '-'}
      </td>
      <td className="p-4 text-center">{account.total_msgs || 0}</td>
      <td className="p-4 text-center">{account.loaded_msgs || 0}</td>
      <td className="p-4 w-48">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <div className="flex-1 h-2 bg-blue-100 rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500 rounded-full transition-all duration-300"
                style={{ width: `${account.status === 'completed' ? 100 : (account.progress || 0)}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 w-8 text-right">
              {account.status === 'completed' ? 100 : (account.progress || 0)}%
            </span>
          </div>
          {account.status === 'processing' && (
            <div className="text-xs text-blue-500 transform scale-90 origin-left animate-pulse">
              {(account.progress || 0) === 0 ? 'Starting...' : 'Syncing...'}
            </div>
          )}
        </div>
      </td>
      <td className="p-4 text-center">
        <div className="flex flex-col items-center gap-1">
          {account.status === 'completed' ? (
            hasIssues ? (
              <div 
                className="flex items-center gap-1 cursor-pointer hover:bg-yellow-100 rounded px-1"
                onClick={onShowLog}
                title="Completed with issues"
              >
                <AlertTriangle className="w-4 h-4 text-yellow-500" />
                <span className="text-xs text-yellow-600">Issues</span>
              </div>
            ) : (
              <CheckCircle className="w-4 h-4 text-green-500" title="Completed" />
            )
          ) : account.status === 'failed' ? (
            <div className="group relative">
              <AlertCircle className="w-4 h-4 text-red-500 cursor-help" />
              {account.error_message && (
                <div className="absolute z-10 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-opacity duration-150 bg-gray-800 text-white text-xs rounded py-2 px-3 -left-32 bottom-full mb-2 w-64 whitespace-normal">
                  {account.error_message}
                  <div className="absolute left-1/2 -bottom-1 transform -translate-x-1/2 w-2 h-2 bg-gray-800 rotate-45" />
                </div>
              )}
            </div>
          ) : (account.status === 'processing' || account.status === 'pending') ? (
            <RefreshCw className="w-4 h-4 text-blue-500 animate-spin" title="Syncing" />
          ) : (
            <Circle className="w-4 h-4 text-gray-300" title="Pending" />
          )}
          <span className="text-xs text-gray-400">
            {account.status === 'completed' ? 'Done' : 
             account.status === 'failed' ? 'Failed' : 
             account.status === 'processing' ? 'Syncing' : 
             account.status === 'pending' ? 'Pending' : 'Ready'}
          </span>
          {account.sync_logs && (
            <button
              onClick={onShowLog}
              className="text-xs text-blue-500 hover:text-blue-700 hover:underline flex items-center gap-0.5"
              title="View sync logs"
            >
              <FileText className="w-3 h-3" />
              Log
            </button>
          )}
        </div>
      </td>
      <td className="p-4 text-center">
        <div className="flex gap-1 justify-center">
          <button 
            className="p-1 hover:bg-green-100 rounded text-green-600 disabled:opacity-50"
            onClick={() => onSync('fast')}
            disabled={account.status === 'processing'}
            title="Fast sync"
          >
            <Zap className="w-4 h-4" />
          </button>
          <button 
            className="p-1 hover:bg-blue-100 rounded text-blue-600 disabled:opacity-50"
            onClick={() => onSync('deep')}
            disabled={account.status === 'processing'}
            title="Deep sync"
          >
            <Database className="w-4 h-4" />
          </button>
          <button 
            className="p-1 hover:bg-orange-100 rounded text-orange-600 disabled:opacity-50"
            onClick={onFixMissing}
            disabled={account.status === 'processing'}
            title="Fix missing data"
          >
            <Wrench className="w-4 h-4" />
          </button>
        </div>
      </td>
    </tr>
  );
};

/**
 * Account Table Component
 * 
 * Displays a table of accounts with:
 * - Selection checkboxes
 * - Account info (avatar, name, fans)
 * - Sync status and progress
 * - Action buttons
 */
export const AccountTable = ({
  accounts,
  selectedIds,
  onToggleSelect,
  onToggleSelectAll,
  onSync,
  onFixMissing,
  onShowLog,
  loading
}) => {
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full text-sm text-left">
        <thead className="text-gray-500 bg-gray-50 border-b">
          <tr>
            <th className="p-4 w-10">
              <input 
                type="checkbox" 
                checked={selectedIds.size === accounts.length && accounts.length > 0} 
                onChange={onToggleSelectAll}
                className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
            </th>
            <th className="p-4">#</th>
            <th className="p-4">Avatar</th>
            <th className="p-4">Name</th>
            <th className="p-4">Fans</th>
            <th className="p-4">Last Sync</th>
            <th className="p-4 text-center">Total</th>
            <th className="p-4 text-center">Synced</th>
            <th className="p-4">Progress</th>
            <th className="p-4 text-center">Status</th>
            <th className="p-4 text-center">Actions</th>
          </tr>
        </thead>
        <tbody>
          {accounts.length === 0 ? (
            <tr>
              <td colSpan="11" className="p-8 text-center text-gray-400">
                {loading ? 'Loading...' : 'No data, click "Add" to add accounts'}
              </td>
            </tr>
          ) : (
            accounts.map((account, index) => (
              <AccountRow
                key={account.id}
                account={account}
                index={index}
                isSelected={selectedIds.has(account.id)}
                onToggleSelect={() => onToggleSelect(account.id)}
                onSync={(mode) => onSync(account.id, mode)}
                onFixMissing={() => onFixMissing(account.id)}
                onShowLog={() => onShowLog(account)}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};

export default AccountTable;

import React from 'react';
import { Search, RefreshCw, ChevronDown, Coffee, Download as DownloadIcon, Play } from 'lucide-react';

export const DownloadPage = () => {
  return (
    <div className="flex-1 bg-gray-50 p-6 overflow-auto flex flex-col">
      <div className="bg-white p-4 rounded-lg shadow-sm border mb-4 space-y-4">
        {/* Filters Row 1 */}
        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">博主选择</label>
            <div className="relative">
              <select className="w-full border rounded-md px-3 py-2 text-sm appearance-none bg-white text-gray-500">
                <option>请选择博主 (可多选)</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>
          <div className="w-48">
            <label className="block text-xs text-gray-500 mb-1">时间范围</label>
            <div className="relative">
              <select className="w-full border rounded-md px-3 py-2 text-sm appearance-none bg-white text-gray-900">
                <option>全部时间</option>
                <option>最近一天</option>
                <option>最近一周</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>
        </div>

        {/* Filters Row 2 */}
        <div className="flex gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs text-gray-500 mb-1">标题搜索 (支持多个关键词, 用空格分隔)</label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input 
                type="text" 
                placeholder="输入标题关键词, 多个关键词用空格分隔"
                className="w-full border rounded-md pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-red-500"
              />
            </div>
          </div>
          <div className="w-48">
            <label className="block text-xs text-gray-500 mb-1">匹配模式</label>
            <div className="relative">
              <select className="w-full border rounded-md px-3 py-2 text-sm appearance-none bg-white text-gray-900">
                <option>AND (所有关键词)</option>
                <option>OR (任意关键词)</option>
              </select>
              <ChevronDown className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
            </div>
          </div>
          <button className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600 text-sm flex items-center gap-1 h-[38px]">
            <RefreshCw className="w-4 h-4" /> 刷新数据
          </button>
        </div>
      </div>

      {/* Action Toolbar */}
      <div className="mb-4 flex gap-2">
        <div className="relative">
          <button className="px-4 py-1.5 bg-white border rounded text-gray-600 text-sm flex items-center gap-2 hover:bg-gray-50">
            抓取 <ChevronDown className="w-3 h-3" />
          </button>
        </div>
        <div className="relative">
          <button className="px-4 py-1.5 bg-white border rounded text-gray-600 text-sm flex items-center gap-2 hover:bg-gray-50">
            导出 <ChevronDown className="w-3 h-3" />
          </button>
        </div>
        <button className="px-4 py-1.5 bg-green-500 text-white rounded text-sm hover:bg-green-600">
          调试
        </button>
      </div>

      {/* Table Area */}
      <div className="bg-white rounded-lg shadow-sm border flex-1 flex flex-col min-h-[400px]">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-gray-500 bg-gray-50 border-b">
              <tr>
                <th className="p-4 w-10"><input type="checkbox" /></th>
                <th className="p-4 cursor-pointer hover:bg-gray-100">创建时间 <ChevronDown className="w-3 h-3 inline ml-1" /></th>
                <th className="p-4 cursor-pointer hover:bg-gray-100">博主 <ChevronDown className="w-3 h-3 inline ml-1" /></th>
                <th className="p-4 cursor-pointer hover:bg-gray-100">发布时间 <ChevronDown className="w-3 h-3 inline ml-1" /></th>
                <th className="p-4 cursor-pointer hover:bg-gray-100">标题 <ChevronDown className="w-3 h-3 inline ml-1" /></th>
                <th className="p-4">链接</th>
                <th className="p-4 cursor-pointer hover:bg-gray-100">阅读 <ChevronDown className="w-3 h-3 inline ml-1" /></th>
              </tr>
            </thead>
            <tbody>
              {/* Empty State */}
            </tbody>
          </table>
        </div>
        
        <div className="flex-1 flex flex-col items-center justify-center text-gray-400 p-10">
          <Coffee className="w-12 h-12 mb-4 text-gray-300" />
          <p>暂无数据</p>
        </div>
      </div>
    </div>
  );
};


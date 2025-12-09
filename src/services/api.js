/**
 * API 服务层 - 统一管理所有 API 请求
 */

const BASE_URL = '/api';

// Cookie 失效事件名
export const COOKIE_INVALID_EVENT = 'cookie-invalid';

// 触发 Cookie 失效事件
const emitCookieInvalid = () => {
  window.dispatchEvent(new CustomEvent(COOKIE_INVALID_EVENT));
};

/**
 * 统一请求处理
 */
class ApiService {
  /**
   * 发送请求
   * @param {string} endpoint - API 端点
   * @param {object} options - 请求选项
   */
  async request(endpoint, options = {}) {
    const url = `${BASE_URL}${endpoint}`;
    
    const config = {
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      ...options,
    };

    // 如果是 GET 请求且有 params，转换为查询字符串
    let finalUrl = url;
    if (options.params && options.method !== 'POST') {
      const searchParams = new URLSearchParams();
      Object.entries(options.params).forEach(([key, value]) => {
        if (value !== undefined && value !== null && value !== '') {
          searchParams.append(key, value);
        }
      });
      const queryString = searchParams.toString();
      if (queryString) {
        finalUrl = `${url}?${queryString}`;
      }
    }

    try {
      const response = await fetch(finalUrl, config);
      
      // 解析响应
      const data = await response.json();
      
      if (!response.ok) {
        const error = new ApiError(data.error || data.message || '请求失败', response.status, data);
        
        // 检测是否是 Cookie 失效相关错误
        if (this.isCookieInvalidError(error, data)) {
          emitCookieInvalid();
        }
        
        throw error;
      }
      
      return data;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      throw new ApiError(error.message || '网络错误', 0);
    }
  }

  /**
   * 判断是否是 Cookie 失效错误
   */
  isCookieInvalidError(error, data) {
    // 检测常见的 Cookie 失效标志
    const invalidKeywords = ['cookie', '登录', '未授权', 'unauthorized', 'auth', '失效', '过期'];
    const errorMsg = (error.message || '').toLowerCase();
    const dataMsg = JSON.stringify(data || {}).toLowerCase();
    
    return invalidKeywords.some(keyword => 
      errorMsg.includes(keyword) || dataMsg.includes(keyword)
    ) || error.status === 401;
  }

  get(endpoint, params) {
    return this.request(endpoint, { method: 'GET', params });
  }

  post(endpoint, data) {
    return this.request(endpoint, { 
      method: 'POST', 
      body: JSON.stringify(data) 
    });
  }

  delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  }
}

/**
 * 自定义 API 错误类
 */
class ApiError extends Error {
  constructor(message, status, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

// 创建单例实例
const api = new ApiService();

// ==================== 账号相关 API ====================

export const accountApi = {
  /**
   * 获取所有账号列表
   */
  getAll: () => api.get('/accounts'),

  /**
   * 获取单个账号
   */
  getById: (id) => api.get(`/accounts/${id}`),

  /**
   * 添加账号
   */
  add: (data) => api.post('/accounts', data),

  /**
   * 删除账号
   */
  delete: (id) => api.delete(`/accounts/${id}`),

  /**
   * 批量删除账号
   */
  batchDelete: (ids) => api.post('/accounts/batch-delete', { ids }),

  /**
   * 同步单个账号
   */
  sync: (id) => api.post(`/accounts/${id}/sync`),

  /**
   * 批量同步账号
   */
  batchSync: (ids) => api.post('/accounts/sync-batch', { ids }),

  /**
   * 同步所有账号
   */
  syncAll: () => api.post('/accounts/sync-all'),

  /**
   * 清空数据库
   */
  reset: () => api.post('/reset'),
};

// ==================== 笔记相关 API ====================

export const noteApi = {
  /**
   * 获取笔记列表
   * @param {object} params - 查询参数
   */
  getAll: (params = {}) => api.get('/notes', params),

  /**
   * 获取单个笔记
   */
  getById: (noteId) => api.get(`/notes/${noteId}`),

  /**
   * 删除笔记
   */
  delete: (noteId) => api.delete(`/notes/${noteId}`),

  /**
   * 批量删除笔记
   */
  batchDelete: (noteIds) => api.post('/notes/batch-delete', { note_ids: noteIds }),

  /**
   * 获取笔记统计
   */
  getStats: () => api.get('/notes/stats'),

  /**
   * 导出笔记
   */
  export: (noteIds, format = 'json') => api.post('/notes/export', { note_ids: noteIds, format }),
};

// ==================== 认证相关 API ====================

export const authApi = {
  /**
   * 获取当前用户信息
   * @param {boolean} forceCheck - 是否强制验证 Cookie
   */
  getCurrentUser: (forceCheck = false) => api.get('/user/me', { force_check: forceCheck }),

  /**
   * 登录
   */
  login: () => api.post('/login'),

  /**
   * 手动添加 Cookie
   */
  setManualCookie: (cookies) => api.post('/cookie/manual', { cookies }),

  /**
   * 检查 Cookie 有效性（强制验证）
   */
  checkCookie: () => api.post('/cookie/check'),

  /**
   * 标记 Cookie 失效
   */
  invalidateCookie: () => api.post('/cookie/invalidate'),

  /**
   * 登出
   */
  logout: () => api.post('/logout'),
};

// ==================== 搜索相关 API ====================

export const searchApi = {
  /**
   * 搜索用户
   */
  searchUsers: (keyword, limit = 10) => api.get('/search/users', { keyword, limit }),

  /**
   * 搜索笔记
   */
  searchNotes: (params) => api.get('/search/notes', params),
};

// 导出错误类供外部使用
export { ApiError };

// 默认导出
export default {
  account: accountApi,
  note: noteApi,
  auth: authApi,
  search: searchApi,
};


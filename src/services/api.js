/**
 * API 服务层 - 统一管理所有 API 请求
 * 
 * 适配后端统一响应格式:
 * 成功: { success: true, message: '...', data: ... }
 * 失败: { success: false, error: { code: '...', message: '...' } }
 */

// API 版本，可切换为 '/api/v1' 使用新版本
const BASE_URL = '/api';

// Cookie 失效事件名
export const COOKIE_INVALID_EVENT = 'cookie-invalid';

// 触发 Cookie 失效事件
const emitCookieInvalid = () => {
  window.dispatchEvent(new CustomEvent(COOKIE_INVALID_EVENT));
};

/**
 * 自定义 API 错误类
 */
class ApiError extends Error {
  constructor(message, status, data = null, errorCode = 'UNKNOWN') {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
    this.errorCode = errorCode;
  }
}

/**
 * 统一请求处理
 */
class ApiService {
  constructor() {
    // 可配置的管理员 API Key（用于危险操作）
    this.adminApiKey = null;
  }

  /**
   * 设置管理员 API Key
   */
  setAdminApiKey(key) {
    this.adminApiKey = key;
  }

  /**
   * 发送请求
   * @param {string} endpoint - API 端点
   * @param {object} options - 请求选项
   * @param {boolean} requireAdmin - 是否需要管理员权限
   */
  async request(endpoint, options = {}, requireAdmin = false) {
    const url = `${BASE_URL}${endpoint}`;
    const isSyncRequest = endpoint.includes('sync');
    
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    // 添加管理员 API Key
    if (requireAdmin && this.adminApiKey) {
      headers['X-API-Key'] = this.adminApiKey;
    }

    const config = {
      headers,
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

    // 同步相关请求添加调试日志
    if (isSyncRequest) {
      console.log('[API调试] 发送同步请求:', {
        url: finalUrl,
        method: options.method || 'GET',
        body: options.body ? JSON.parse(options.body) : null
      });
    }

    try {
      const response = await fetch(finalUrl, config);
      
      // 解析响应
      const data = await response.json();
      
      // 同步相关请求添加调试日志
      if (isSyncRequest) {
        console.log('[API调试] 同步请求响应:', {
          url: finalUrl,
          status: response.status,
          ok: response.ok,
          data: data
        });
      }
      
      if (!response.ok) {
        // 新的错误响应格式
        const errorMessage = data.error?.message || data.message || data.error || '请求失败';
        const errorCode = data.error?.code || 'UNKNOWN';
        const error = new ApiError(errorMessage, response.status, data, errorCode);
        
        if (isSyncRequest) {
          console.error('[API调试] 同步请求失败:', {
            url: finalUrl,
            errorMessage,
            errorCode,
            status: response.status,
            fullData: data
          });
        }
        
        // 检测是否是 Cookie 失效相关错误
        if (this.isCookieInvalidError(error, data)) {
          emitCookieInvalid();
        }
        
        throw error;
      }
      
      // 新的成功响应格式：返回 data 字段或整个响应
      // 兼容旧格式（直接返回数组）和新格式（{ success, data }）
      if (data.success !== undefined) {
        return data.data !== undefined ? data.data : data;
      }
      
      return data;
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      if (isSyncRequest) {
        console.error('[API调试] 同步请求网络错误:', error);
      }
      throw new ApiError(error.message || '网络错误', 0);
    }
  }

  /**
   * 判断是否是 Cookie 失效错误
   */
  isCookieInvalidError(error, data) {
    // 检查错误代码
    if (data.error?.code === 'UNAUTHORIZED' || data.error?.code === 'INVALID_COOKIE') {
      return true;
    }
    
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

  post(endpoint, data, requireAdmin = false) {
    return this.request(endpoint, { 
      method: 'POST', 
      body: JSON.stringify(data) 
    }, requireAdmin);
  }

  delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
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
   * @param {number} id - 账号ID
   * @param {string} mode - 同步模式 'fast' | 'deep'
   */
  sync: (id, mode = 'fast') => api.post(`/accounts/${id}/sync`, { mode }),

  /**
   * 批量同步账号
   * @param {array} ids - 账号ID列表
   * @param {string} mode - 同步模式 'fast' | 'deep'
   */
  batchSync: (ids, mode = 'fast') => api.post('/accounts/sync-batch', { ids, mode }),

  /**
   * 同步所有账号
   * @param {string} mode - 同步模式 'fast' | 'deep'
   */
  syncAll: (mode = 'fast') => api.post('/accounts/sync-all', { mode }),

  /**
   * 停止同步
   */
  stopSync: () => api.post('/accounts/stop-sync'),

  /**
   * 补齐缺失字段（发布时间等）
   * @param {number} id - 账号ID
   * @param {boolean} force - 是否强制重新采集所有笔记
   */
  fixMissing: (id, force = false) => api.post(`/accounts/${id}/fix-missing`, { force }),

  /**
   * 获取所有博主的缺失字段统计
   */
  getMissingStats: () => api.get('/accounts/stats/missing'),

  /**
   * 清空数据库（需要管理员权限）
   */
  reset: () => api.post('/reset', {}, true),
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
   * @param {Array} noteIds - 要导出的笔记ID列表，为空时导出筛选结果
   * @param {string} format - 导出格式，默认 json
   * @param {Object} filterParams - 筛选条件参数（当 noteIds 为空时使用）
   */
  export: (noteIds, format = 'json', filterParams = {}) => api.post('/notes/export', { 
    note_ids: noteIds, 
    format,
    ...filterParams
  }),
};

// ==================== 加密工具 ====================

/**
 * AES-256-CBC 加密（用于 Cookie 传输加密）
 */
class CookieEncryption {
  constructor() {
    this.key = null;
    this.keyPromise = null;
  }

  /**
   * 获取传输加密密钥
   */
  async getKey() {
    if (this.key) return this.key;
    
    if (!this.keyPromise) {
      this.keyPromise = api.get('/cookie/transport-key').then(data => {
        this.key = data.key;
        return this.key;
      });
    }
    
    return this.keyPromise;
  }

  /**
   * 加密 Cookie 字符串
   * 使用 AES-256-CBC 加密
   */
  async encrypt(cookieStr) {
    const keyBase64 = await this.getKey();
    
    // 检查是否支持 Web Crypto API
    if (window.crypto && window.crypto.subtle) {
      try {
        // 将 Base64 密钥转换为 ArrayBuffer
        const keyBytes = Uint8Array.from(atob(keyBase64), c => c.charCodeAt(0));
        
        // 生成随机 IV
        const iv = window.crypto.getRandomValues(new Uint8Array(16));
        
        // 导入密钥
        const cryptoKey = await window.crypto.subtle.importKey(
          'raw',
          keyBytes,
          { name: 'AES-CBC' },
          false,
          ['encrypt']
        );
        
        // 加密数据（需要手动添加 PKCS7 填充）
        const encoder = new TextEncoder();
        const data = encoder.encode(cookieStr);
        const paddingLength = 16 - (data.length % 16);
        const paddedData = new Uint8Array(data.length + paddingLength);
        paddedData.set(data);
        paddedData.fill(paddingLength, data.length);
        
        const encrypted = await window.crypto.subtle.encrypt(
          { name: 'AES-CBC', iv },
          cryptoKey,
          paddedData
        );
        
        // 转换为 Base64
        const encryptedBase64 = btoa(String.fromCharCode(...new Uint8Array(encrypted)));
        const ivBase64 = btoa(String.fromCharCode(...iv));
        
        return { encrypted: encryptedBase64, iv: ivBase64 };
      } catch (error) {
        console.warn('Web Crypto API encryption failed, falling back to XOR:', error);
        return this.simpleEncrypt(cookieStr, keyBase64);
      }
    } else {
      // 后备方案：简单 XOR 加密
      return this.simpleEncrypt(cookieStr, keyBase64);
    }
  }

  /**
   * 简单 XOR 加密（后备方案）
   */
  simpleEncrypt(text, keyBase64) {
    const keyBytes = Uint8Array.from(atob(keyBase64), c => c.charCodeAt(0));
    const textBytes = new TextEncoder().encode(text);
    const result = new Uint8Array(textBytes.length);
    
    for (let i = 0; i < textBytes.length; i++) {
      result[i] = textBytes[i] ^ keyBytes[i % keyBytes.length];
    }
    
    return {
      encrypted: 'XOR:' + btoa(String.fromCharCode(...result)),
      iv: ''
    };
  }
}

// 全局加密实例
const cookieEncryption = new CookieEncryption();

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
   * 手动添加 Cookie（明文传输 - 不推荐）
   */
  setManualCookie: (cookies) => api.post('/cookie/manual', { 
    cookies,
    filled_at: new Date().toISOString(),
  }),

  /**
   * 手动添加 Cookie（加密传输 - 推荐）
   */
  setManualCookieEncrypted: async (cookies) => {
    const { encrypted, iv } = await cookieEncryption.encrypt(cookies);
    return api.post('/cookie/manual-encrypted', { 
      encrypted_cookies: encrypted, 
      iv,
      filled_at: new Date().toISOString(),
    });
  },

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

  /**
   * 获取 Cookie 历史记录
   */
  getCookieHistory: () => api.get('/cookie/history'),

  /**
   * 重新激活历史 Cookie
   */
  reactivateCookie: (cookieId) => api.post(`/cookie/reactivate/${cookieId}`),

  /**
   * 获取传输加密密钥
   */
  getTransportKey: () => api.get('/cookie/transport-key'),
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

// ==================== 工具函数 ====================

/**
 * 设置管理员 API Key
 * 用于执行危险操作（如清空数据库）
 */
export const setAdminApiKey = (key) => {
  api.setAdminApiKey(key);
};

// 导出错误类供外部使用
export { ApiError };

// 默认导出
export default {
  account: accountApi,
  note: noteApi,
  auth: authApi,
  search: searchApi,
  setAdminApiKey,
};

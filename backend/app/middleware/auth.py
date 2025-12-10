"""
认证中间件
用于保护敏感 API 端点
"""
import os
from functools import wraps
from flask import request, g
from ..utils.responses import ApiResponse


def get_current_api_key() -> str:
    """从请求头获取 API Key"""
    return request.headers.get('X-API-Key', '')


def require_auth(f):
    """
    基础认证装饰器
    
    检查请求头中的 X-API-Key
    如果环境变量 API_KEY 未设置，则跳过验证（开发模式）
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = get_current_api_key()
        expected_key = os.environ.get('API_KEY')
        
        # 开发模式：如果未设置 API_KEY，跳过验证
        if not expected_key:
            return f(*args, **kwargs)
        
        if not api_key:
            return ApiResponse.unauthorized('缺少 API Key，请在请求头中添加 X-API-Key')
        
        if api_key != expected_key:
            return ApiResponse.unauthorized('无效的 API Key')
        
        return f(*args, **kwargs)
    return decorated


def require_admin(f):
    """
    管理员认证装饰器
    
    用于保护危险操作（如清空数据库）
    需要 ADMIN_API_KEY 环境变量
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = get_current_api_key()
        admin_key = os.environ.get('ADMIN_API_KEY')
        
        # 如果未设置管理员密钥，禁止所有访问
        if not admin_key:
            return ApiResponse.forbidden(
                '此操作需要管理员权限，请配置 ADMIN_API_KEY 环境变量'
            )
        
        if not api_key:
            return ApiResponse.unauthorized('缺少管理员 API Key')
        
        if api_key != admin_key:
            return ApiResponse.forbidden('无效的管理员 API Key')
        
        return f(*args, **kwargs)
    return decorated


def optional_auth(f):
    """
    可选认证装饰器
    
    如果提供了 API Key 则验证，否则跳过
    用于某些可以匿名访问但认证后有更多权限的端点
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = get_current_api_key()
        expected_key = os.environ.get('API_KEY')
        
        g.is_authenticated = False
        
        if api_key and expected_key and api_key == expected_key:
            g.is_authenticated = True
        
        return f(*args, **kwargs)
    return decorated


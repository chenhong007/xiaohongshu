"""
统一 API 响应格式
"""
from flask import jsonify
from typing import Any, Optional, Dict


class ApiResponse:
    """API 响应构建器"""
    
    @staticmethod
    def success(data: Any = None, message: str = '操作成功') -> tuple:
        """
        成功响应
        
        Args:
            data: 响应数据
            message: 成功消息
            
        Returns:
            Flask Response 对象
        """
        response = {
            'success': True,
            'message': message,
        }
        if data is not None:
            response['data'] = data
        return jsonify(response), 200
    
    @staticmethod
    def created(data: Any = None, message: str = '创建成功') -> tuple:
        """创建成功响应 (201)"""
        response = {
            'success': True,
            'message': message,
        }
        if data is not None:
            response['data'] = data
        return jsonify(response), 201
    
    @staticmethod
    def error(
        message: str,
        code: int = 400,
        error_code: str = 'BAD_REQUEST',
        details: Optional[Dict] = None
    ) -> tuple:
        """
        错误响应
        
        Args:
            message: 错误消息
            code: HTTP 状态码
            error_code: 错误代码
            details: 详细错误信息
            
        Returns:
            Flask Response 对象和状态码的元组
        """
        response = {
            'success': False,
            'error': {
                'code': error_code,
                'message': message,
            }
        }
        if details:
            response['error']['details'] = details
        return jsonify(response), code
    
    @staticmethod
    def not_found(message: str = '资源不存在') -> tuple:
        """404 响应"""
        return ApiResponse.error(message, 404, 'NOT_FOUND')
    
    @staticmethod
    def unauthorized(message: str = '未授权的请求') -> tuple:
        """401 响应"""
        return ApiResponse.error(message, 401, 'UNAUTHORIZED')
    
    @staticmethod
    def forbidden(message: str = '禁止访问') -> tuple:
        """403 响应"""
        return ApiResponse.error(message, 403, 'FORBIDDEN')
    
    @staticmethod
    def validation_error(message: str, details: Optional[Dict] = None) -> tuple:
        """验证错误响应"""
        return ApiResponse.error(message, 400, 'VALIDATION_ERROR', details)
    
    @staticmethod
    def server_error(message: str = '服务器内部错误') -> tuple:
        """500 响应"""
        return ApiResponse.error(message, 500, 'INTERNAL_ERROR')


# 便捷函数
def success_response(data: Any = None, message: str = '操作成功') -> tuple:
    """成功响应的快捷方式"""
    return ApiResponse.success(data, message)


def error_response(
    message: str,
    code: int = 400,
    error_code: str = 'BAD_REQUEST',
    details: Optional[Dict] = None
) -> tuple:
    """错误响应的快捷方式"""
    return ApiResponse.error(message, code, error_code, details)


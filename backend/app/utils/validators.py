"""
输入验证工具
"""
import re
from typing import List, Tuple, Optional, Any


def validate_user_id(user_id: Any) -> Tuple[bool, Optional[str]]:
    """
    验证小红书用户 ID 格式
    
    Args:
        user_id: 用户 ID
        
    Returns:
        (is_valid, error_message)
    """
    if not user_id:
        return False, '用户 ID 不能为空'
    
    if not isinstance(user_id, str):
        return False, '用户 ID 必须是字符串'
    
    # 去除首尾空格
    user_id = user_id.strip()
    
    if len(user_id) < 5:
        return False, '用户 ID 长度不能少于 5 个字符'
    
    if len(user_id) > 64:
        return False, '用户 ID 长度不能超过 64 个字符'
    
    # 小红书用户 ID 通常是字母数字组合
    if not re.match(r'^[a-zA-Z0-9_-]+$', user_id):
        return False, '用户 ID 只能包含字母、数字、下划线和连字符'
    
    return True, None


def validate_ids_list(
    ids: Any,
    max_count: int = 100,
    field_name: str = 'IDs'
) -> Tuple[bool, Optional[str], List[int]]:
    """
    验证 ID 列表
    
    Args:
        ids: ID 列表
        max_count: 最大允许数量
        field_name: 字段名称（用于错误消息）
        
    Returns:
        (is_valid, error_message, cleaned_ids)
    """
    if not ids:
        return False, f'{field_name} 不能为空', []
    
    if not isinstance(ids, list):
        return False, f'{field_name} 必须是数组', []
    
    if len(ids) > max_count:
        return False, f'{field_name} 数量不能超过 {max_count} 个', []
    
    # 验证每个 ID 都是整数
    cleaned_ids = []
    for i, id_val in enumerate(ids):
        try:
            cleaned_id = int(id_val)
            if cleaned_id <= 0:
                return False, f'{field_name}[{i}] 必须是正整数', []
            cleaned_ids.append(cleaned_id)
        except (TypeError, ValueError):
            return False, f'{field_name}[{i}] 不是有效的整数', []
    
    return True, None, cleaned_ids


def validate_cookie_str(cookie_str: Any) -> Tuple[bool, Optional[str]]:
    """
    验证 Cookie 字符串
    
    Args:
        cookie_str: Cookie 字符串
        
    Returns:
        (is_valid, error_message)
    """
    if not cookie_str:
        return False, 'Cookie 不能为空'
    
    if not isinstance(cookie_str, str):
        return False, 'Cookie 必须是字符串'
    
    cookie_str = cookie_str.strip()
    
    if len(cookie_str) < 50:
        return False, 'Cookie 字符串太短，请确保复制了完整的 Cookie'
    
    if len(cookie_str) > 10000:
        return False, 'Cookie 字符串过长'
    
    # 检查必须的 Cookie 字段
    required_fields = ['a1']
    for field in required_fields:
        if field not in cookie_str:
            return False, f"Cookie 缺少必要字段 '{field}'"
    
    return True, None


def validate_sync_mode(mode: Any) -> Tuple[bool, Optional[str], str]:
    """
    验证同步模式
    
    Args:
        mode: 同步模式
        
    Returns:
        (is_valid, error_message, cleaned_mode)
    """
    valid_modes = ['fast', 'deep']
    
    if not mode:
        return True, None, 'fast'  # 默认快速模式
    
    if not isinstance(mode, str):
        return False, '同步模式必须是字符串', ''
    
    mode = mode.lower().strip()
    
    if mode not in valid_modes:
        return False, f"无效的同步模式，必须是 {valid_modes} 之一", ''
    
    return True, None, mode


def sanitize_string(value: Any, max_length: int = 255, default: str = '') -> str:
    """
    清理字符串输入
    
    Args:
        value: 输入值
        max_length: 最大长度
        default: 默认值
        
    Returns:
        清理后的字符串
    """
    if not value:
        return default
    
    if not isinstance(value, str):
        value = str(value)
    
    # 去除首尾空格
    value = value.strip()
    
    # 截断过长的字符串
    if len(value) > max_length:
        value = value[:max_length]
    
    return value


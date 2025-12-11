"""
输入验证工具
"""
import re
from datetime import datetime, timedelta, timezone
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


def validate_filled_at(
    filled_at: Any,
    field_name: str = '填写时间',
    future_tolerance_seconds: int = 300
) -> Tuple[bool, Optional[str], Optional[datetime]]:
    """
    验证用户填写 Cookie 的时间
    支持 ISO8601 字符串或时间戳（秒/毫秒）
    
    Returns:
        (is_valid, error_message, parsed_datetime_utc)
    """
    if filled_at is None:
        return True, None, None
    
    # 允许空字符串直接忽略
    if isinstance(filled_at, str) and not filled_at.strip():
        return True, None, None
    
    parsed_dt: Optional[datetime] = None
    
    def _ts_to_dt(value: float) -> datetime:
        # 支持毫秒时间戳
        if value > 1e12:
            value = value / 1000.0
        return datetime.fromtimestamp(value, tz=timezone.utc)
    
    if isinstance(filled_at, (int, float)):
        try:
            parsed_dt = _ts_to_dt(float(filled_at))
        except Exception:
            pass
    elif isinstance(filled_at, str):
        ts_str = filled_at.strip()
        # 先尝试 ISO8601
        try:
            iso_str = ts_str.replace('Z', '+00:00') if ts_str.endswith('Z') else ts_str
            parsed_dt = datetime.fromisoformat(iso_str)
        except ValueError:
            # 再尝试数字时间戳
            try:
                parsed_dt = _ts_to_dt(float(ts_str))
            except Exception:
                pass
    
    if not parsed_dt:
        return False, f'{field_name} 格式不正确', None
    
    # 统一为 UTC naive
    if parsed_dt.tzinfo:
        parsed_dt = parsed_dt.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        parsed_dt = parsed_dt.replace(tzinfo=None)
    
    # 不允许明显晚于当前时间，避免前端时间异常导致负运行时长
    now_utc = datetime.utcnow()
    if parsed_dt - now_utc > timedelta(seconds=future_tolerance_seconds):
        return False, f'{field_name} 不能晚于当前时间', None
    
    return True, None, parsed_dt


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


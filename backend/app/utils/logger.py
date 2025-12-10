"""
日志配置模块
使用 loguru 提供结构化日志
"""
import os
import sys
from loguru import logger
from typing import Optional


def setup_logger(
    log_level: str = 'INFO',
    log_file: Optional[str] = None,
    rotation: str = '10 MB',
    retention: str = '7 days'
) -> None:
    """
    配置日志系统
    
    Args:
        log_level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_file: 日志文件路径（可选）
        rotation: 日志轮转大小
        retention: 日志保留时间
    """
    # 移除默认处理器
    logger.remove()
    
    # 从环境变量获取日志级别
    level = os.environ.get('LOG_LEVEL', log_level).upper()
    
    # 控制台输出格式
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )
    
    # 添加控制台处理器
    logger.add(
        sys.stderr,
        format=console_format,
        level=level,
        colorize=True,
        backtrace=True,
        diagnose=True,
    )
    
    # 如果指定了日志文件，添加文件处理器
    if log_file:
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        )
        logger.add(
            log_file,
            format=file_format,
            level=level,
            rotation=rotation,
            retention=retention,
            compression='zip',
            encoding='utf-8',
        )
    
    logger.info(f"Logger initialized with level: {level}")


def get_logger(name: str = None):
    """
    获取日志器实例
    
    Args:
        name: 日志器名称
        
    Returns:
        logger 实例
    """
    if name:
        return logger.bind(name=name)
    return logger


# 便捷的日志函数
def log_api_request(method: str, path: str, params: dict = None):
    """记录 API 请求"""
    logger.info(f"API Request: {method} {path}", extra={'params': params})


def log_api_response(path: str, status: int, duration_ms: float = None):
    """记录 API 响应"""
    if duration_ms:
        logger.info(f"API Response: {path} -> {status} ({duration_ms:.2f}ms)")
    else:
        logger.info(f"API Response: {path} -> {status}")


def log_sync_event(account_id: int, event: str, details: dict = None):
    """记录同步事件"""
    msg = f"Sync Event: account={account_id}, event={event}"
    if details:
        msg += f", details={details}"
    logger.info(msg)


def log_error(error: Exception, context: str = None):
    """记录错误"""
    if context:
        logger.error(f"Error in {context}: {error}")
    else:
        logger.error(f"Error: {error}")
    logger.exception(error)


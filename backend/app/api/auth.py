"""
认证相关 API

注意：Cookie 验证逻辑已统一封装到 CookieService 中
所有 Cookie 相关操作都应使用 CookieService 的方法
"""
from flask import Blueprint, request, current_app
from datetime import datetime

from ..extensions import db
from ..models import Cookie, Account
from ..utils.responses import ApiResponse, success_response
from ..utils.validators import validate_cookie_str, validate_filled_at
from ..utils.crypto import encrypt_cookie, decrypt_cookie, get_crypto
from ..utils.logger import get_logger
from ..services.cookie_service import CookieService

auth_bp = Blueprint('auth', __name__)
logger = get_logger('auth')


def reset_account_errors():
    """
    清理账号同步的历史错误状态，避免旧的 Cookie 失效信息反复触发
    """
    try:
        Account.query.filter(Account.status == 'failed').update(
            {
                'status': 'pending',
                'error_message': None,
                'progress': 0
            },
            synchronize_session=False
        )
        db.session.commit()
        logger.info("已清理账号的失败状态和错误信息")
    except Exception as e:
        db.session.rollback()
        logger.error(f"清理账号错误状态失败: {e}")


# ============================================================
# 以下函数保留为兼容性别名，实际调用 CookieService 的方法
# 新代码应直接使用 CookieService
# ============================================================

def get_active_cookie():
    """获取当前激活的 Cookie 字符串（兼容性别名）"""
    return CookieService.get_cookie_str()


def invalidate_cookie(cookie_id=None):
    """标记 Cookie 失效（兼容性别名）"""
    return CookieService.invalidate(cookie_id)


def get_recent_valid_cookie():
    """获取最近的有效历史 Cookie（兼容性别名）"""
    return CookieService.get_recent_valid_cookie()


def should_validate_cookie(cookie):
    """判断是否需要验证 Cookie（兼容性别名）"""
    return CookieService.should_validate(cookie)


def validate_cookie_if_needed(cookie, force=False):
    """按需验证 Cookie（兼容性别名）"""
    return CookieService.validate_if_needed(cookie, force)


def extract_user_info(res_data):
    """从 API 响应中提取用户信息（兼容性别名）"""
    return CookieService._extract_user_info(res_data)


@auth_bp.route('/user/me', methods=['GET'])
def get_current_user():
    """
    获取当前登录用户信息
    
    Query Parameters:
        - force_check: 是否强制验证 Cookie（默认 false）
    
    返回值包含:
        - is_connected: 是否已连接
        - user_id, nickname, avatar: 用户信息
        - run_info: 运行时长信息
        - was_connected: 之前是否连接过（用于显示失效信息）
    """
    force_check = request.args.get('force_check', 'false').lower() == 'true'
    
    # 使用统一的 CookieService 获取和验证 Cookie
    # 优先使用最近的有效历史 Cookie
    cookie = CookieService.get_recent_valid_cookie()
    
    if not cookie:
        # 没有有效 Cookie，尝试获取任何激活的 Cookie（可能已失效）
        cookie = CookieService.get_active_cookie()
    
    if cookie:
        # 使用统一的验证逻辑（会自动处理无效 Cookie 的重新验证）
        if force_check or CookieService.should_validate(cookie):
            is_valid, _ = CookieService.validate_if_needed(cookie, force=force_check)
            if not is_valid:
                # Cookie 失效，返回失效信息和上次运行时长
                run_info = cookie.get_run_info()
                return success_response({
                    'is_connected': False,
                    'was_connected': True,
                    'message': 'Cookie 已失效，请重新登录',
                    'user_id': cookie.user_id,
                    'nickname': cookie.nickname,
                    'avatar': cookie.avatar,
                    'run_info': run_info,
                })
        
        # Cookie 有效，返回用户信息
        if cookie.is_valid:
            # 如果 Cookie 有效但没有启动计时器，自动启动（兼容旧数据）
            if not cookie.run_start_time:
                cookie.start_run_timer()
                db.session.commit()
                logger.info(f"为现有有效 Cookie {cookie.id} 自动启动计时器")
            
            # 检查是否使用了安全加密
            crypto = get_crypto()
            run_info = cookie.get_run_info()
            return success_response({
                'is_connected': True,
                'user_id': cookie.user_id,
                'nickname': cookie.nickname,
                'avatar': cookie.avatar,
                'last_checked': (cookie.last_checked.isoformat() + 'Z') if cookie.last_checked else None,
                'is_secure': crypto.is_secure,  # 告知前端是否安全存储
                'run_info': run_info,
            })
        else:
            # Cookie 已失效，返回失效信息
            run_info = cookie.get_run_info()
            return success_response({
                'is_connected': False,
                'was_connected': True,
                'message': 'Cookie 已失效，请重新登录',
                'user_id': cookie.user_id,
                'nickname': cookie.nickname,
                'avatar': cookie.avatar,
                'run_info': run_info,
            })
    
    # 检查配置中的 Cookie
    cookies_str = current_app.config.get('XHS_COOKIES', '')
    if cookies_str:
        try:
            from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
            xhs_apis = XHS_Apis()
            success, msg, res = xhs_apis.get_user_self_info(cookies_str)
            
            if success and res.get('data'):
                user_id, nickname, avatar = CookieService._extract_user_info(res['data'])
                return success_response({
                    'is_connected': True,
                    'user_id': user_id,
                    'nickname': nickname,
                    'avatar': avatar,
                    'run_info': None,  # 配置中的 Cookie 不统计运行时长
                })
        except Exception as e:
            logger.error(f"Failed to validate cookie: {e}")
    
    return success_response({
        'is_connected': False,
        'message': '未连接小红书账号',
        'run_info': None,
    })


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    触发登录流程
    可以扩展为打开浏览器自动登录获取 Cookie
    """
    return success_response(
        message='请手动添加 Cookie 或使用自动登录脚本'
    )


@auth_bp.route('/cookie/manual', methods=['POST'])
def manual_cookie():
    """
    手动添加 Cookie
    
    Request Body:
        - cookies: Cookie 字符串
    """
    data = request.json or {}
    cookie_str = data.get('cookies', '').strip()
    filled_at_raw = data.get('filled_at')

    # 验证填写时间（可选）
    is_filled_valid, filled_error, filled_at_dt = validate_filled_at(filled_at_raw)
    if not is_filled_valid:
        return ApiResponse.validation_error(filled_error)
    
    # 验证 Cookie 格式
    is_valid, error_msg = validate_cookie_str(cookie_str)
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    # 验证 Cookie 有效性
    try:
        from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        
        # 先用 v1 接口验证
        success, msg, res = xhs_apis.get_user_self_info(cookie_str)
        logger.info(f"[manual_cookie] selfinfo v1: success={success}, msg={msg}")
        
        if not success:
            return ApiResponse.error(f'Cookie 无效: {msg}', 400, 'INVALID_COOKIE')
        
        # 尝试 v2 接口获取更详细的信息
        res2_data = None
        try:
            success2, msg2, res2 = xhs_apis.get_user_self_info2(cookie_str)
            logger.info(f"[manual_cookie] selfinfo v2: success={success2}, msg={msg2}")
            if success2 and res2.get('data'):
                res2_data = res2['data']
                logger.info(f"[manual_cookie] v2 数据: {list(res2_data.keys()) if isinstance(res2_data, dict) else type(res2_data)}")
        except Exception as e:
            logger.warning(f"[manual_cookie] v2 接口调用失败: {e}")
        
        # 优先使用 v2 数据（如果有），否则使用 v1 数据
        data_to_use = res2_data if res2_data else res.get('data', {})
        logger.info(f"[manual_cookie] 使用{'v2' if res2_data else 'v1'}数据提取用户信息")
        
        # 提取用户信息
        user_id, nickname, avatar = extract_user_info(data_to_use)
        
        logger.info(f"Cookie 验证成功: user_id={user_id}, nickname={nickname}, avatar={avatar[:50] if avatar else 'None'}...")
        
        # 检查是否存在同一用户的Cookie（查找所有同用户的记录，不仅仅是激活的）
        # 优先查找激活的，其次查找最近更新的
        existing_cookie = None
        if user_id:
            existing_cookie = Cookie.query.filter_by(user_id=user_id, is_active=True).first()
            if not existing_cookie:
                # 查找同一用户的最近历史记录（用于合并运行时间统计）
                existing_cookie = Cookie.query.filter_by(user_id=user_id).order_by(Cookie.updated_at.desc()).first()
                if existing_cookie:
                    logger.info(f"找到同一用户 {user_id} 的历史Cookie记录 (id={existing_cookie.id})，将合并运行时间统计")
        
        # 将之前的 Cookie 设为非激活
        Cookie.query.update({'is_active': False})
        
        if existing_cookie:
            # 同一用户的Cookie更新：保留原有的运行时间统计
            logger.info(f"检测到同一用户 {user_id} 的Cookie更新，保留原有运行时间统计")
            
            # 更新现有Cookie的内容
            existing_cookie.set_cookie_str(cookie_str)
            existing_cookie.nickname = nickname
            existing_cookie.avatar = avatar
            existing_cookie.is_active = True
            existing_cookie.is_valid = True
            existing_cookie.last_checked = datetime.utcnow()
            # 保留原有的 run_start_time、total_run_seconds 等时间统计
            # 如果之前已失效，重新设置开始时间（优先使用用户提供的 filled_at）
            if not existing_cookie.run_start_time:
                existing_cookie.run_start_time = filled_at_dt if filled_at_dt else datetime.utcnow()
                logger.info(f"Cookie 之前已失效，重新开始计时 (start_time={existing_cookie.run_start_time})")
            
            cookie = existing_cookie
        else:
            # 新用户的Cookie：创建新记录，重新开始计时
            logger.info(f"检测到新用户 {user_id} 的Cookie，重新开始计时")
            
            # 保存新 Cookie（加密存储）
            cookie = Cookie(
                user_id=user_id,
                nickname=nickname,
                avatar=avatar,
                is_active=True,
                is_valid=True,
                last_checked=datetime.utcnow(),
                run_start_time=filled_at_dt if filled_at_dt else datetime.utcnow(),
                total_run_seconds=0,
                last_valid_duration=0,
            )
            # 使用加密方法设置 Cookie
            cookie.set_cookie_str(cookie_str)
            
            db.session.add(cookie)
        
        db.session.commit()

        # 清理历史同步错误，避免旧错误反复触发 Cookie 失效提示
        reset_account_errors()
        
        # 检查是否安全存储
        crypto = get_crypto()
        
        # 获取运行信息
        run_info = cookie.get_run_info()
        
        return success_response(
            data={
                'user_id': user_id,
                'nickname': nickname,
                'avatar': avatar,
                'is_secure': crypto.is_secure,
                'run_info': run_info,
            },
            message='Cookie 添加成功' + ('' if crypto.is_secure else ' (警告: 未启用加密存储)')
        )
        
    except Exception as e:
        logger.error(f"Cookie validation error: {e}")
        return ApiResponse.error(f'Cookie 验证失败: {str(e)}', 400, 'VALIDATION_FAILED')


@auth_bp.route('/cookie/check', methods=['POST'])
def check_cookie():
    """检查当前 Cookie 是否有效（强制验证）"""
    cookie = Cookie.query.filter_by(is_active=True).first()
    
    if not cookie:
        return success_response({
            'is_valid': False,
            'message': '没有激活的 Cookie'
        })
    
    # 强制验证
    is_valid, _ = validate_cookie_if_needed(cookie, force=True)
    
    return success_response({
        'is_valid': is_valid,
        'message': 'Cookie 有效' if is_valid else 'Cookie 已失效',
        'last_checked': (cookie.last_checked.isoformat() + 'Z') if cookie.last_checked else None
    })


@auth_bp.route('/cookie/invalidate', methods=['POST'])
def invalidate_current_cookie():
    """
    标记当前 Cookie 失效
    用于其他 API 调用检测到 Cookie 失效时调用
    """
    success = invalidate_cookie()
    return success_response({
        'success': success,
        'message': 'Cookie 已标记失效' if success else '没有激活的 Cookie'
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """登出（停用当前 Cookie）"""
    Cookie.query.filter_by(is_active=True).update({'is_active': False})
    db.session.commit()
    logger.info("用户已登出")
    return success_response(message='已登出')


@auth_bp.route('/cookie/transport-key', methods=['GET'])
def get_transport_key():
    """
    获取传输加密密钥
    前端使用此密钥加密 Cookie 后再传输
    """
    from ..utils.crypto import get_transport_crypto
    transport_crypto = get_transport_crypto()
    
    return success_response({
        'key': transport_crypto.get_public_key(),
        'algorithm': 'aes-256-cbc',
    })


@auth_bp.route('/cookie/manual-encrypted', methods=['POST'])
def manual_cookie_encrypted():
    """
    接收加密传输的 Cookie
    前端使用 transport-key 加密后发送
    
    Request Body:
        - encrypted_cookies: 加密后的 Cookie 字符串
        - iv: 初始化向量（Base64 编码）
    """
    data = request.json or {}
    encrypted_cookies = data.get('encrypted_cookies', '').strip()
    iv = data.get('iv', '').strip()
    filled_at_raw = data.get('filled_at')

    # 验证填写时间（可选）
    is_filled_valid, filled_error, filled_at_dt = validate_filled_at(filled_at_raw)
    if not is_filled_valid:
        return ApiResponse.validation_error(filled_error)
    
    if not encrypted_cookies:
        return ApiResponse.validation_error('缺少加密的 Cookie 数据')
    
    # 解密传输数据
    try:
        from ..utils.crypto import get_transport_crypto
        transport_crypto = get_transport_crypto()
        cookie_str = transport_crypto.decrypt(encrypted_cookies, iv)
        
        if not cookie_str:
            return ApiResponse.error('Cookie 解密失败', 400, 'DECRYPTION_FAILED')
            
    except Exception as e:
        logger.error(f"Cookie transport decryption error: {e}")
        return ApiResponse.error(f'Cookie 传输解密失败: {str(e)}', 400, 'DECRYPTION_FAILED')
    
    # 验证 Cookie 格式
    is_valid, error_msg = validate_cookie_str(cookie_str)
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    # 后续流程与 manual_cookie 相同
    try:
        from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        
        success, msg, res = xhs_apis.get_user_self_info(cookie_str)
        logger.info(f"[manual_cookie_encrypted] selfinfo v1: success={success}, msg={msg}")
        
        if not success:
            return ApiResponse.error(f'Cookie 无效: {msg}', 400, 'INVALID_COOKIE')
        
        # 尝试 v2 接口
        res2_data = None
        try:
            success2, msg2, res2 = xhs_apis.get_user_self_info2(cookie_str)
            if success2 and res2.get('data'):
                res2_data = res2['data']
        except Exception as e:
            logger.warning(f"[manual_cookie_encrypted] v2 接口调用失败: {e}")
        
        data_to_use = res2_data if res2_data else res.get('data', {})
        user_id, nickname, avatar = extract_user_info(data_to_use)
        
        logger.info(f"Cookie(加密) 验证成功: user_id={user_id}, nickname={nickname}")
        
        # 检查是否存在同一用户的Cookie（查找所有同用户的记录，不仅仅是激活的）
        # 优先查找激活的，其次查找最近更新的
        existing_cookie = None
        if user_id:
            existing_cookie = Cookie.query.filter_by(user_id=user_id, is_active=True).first()
            if not existing_cookie:
                # 查找同一用户的最近历史记录（用于合并运行时间统计）
                existing_cookie = Cookie.query.filter_by(user_id=user_id).order_by(Cookie.updated_at.desc()).first()
                if existing_cookie:
                    logger.info(f"找到同一用户 {user_id} 的历史Cookie记录 (id={existing_cookie.id})，将合并运行时间统计")
        
        # 将之前的 Cookie 设为非激活
        Cookie.query.update({'is_active': False})
        
        if existing_cookie:
            # 同一用户的Cookie更新：保留原有的运行时间统计
            logger.info(f"检测到同一用户 {user_id} 的Cookie更新，保留原有运行时间统计")
            
            # 更新现有Cookie的内容
            existing_cookie.set_cookie_str(cookie_str)
            existing_cookie.nickname = nickname
            existing_cookie.avatar = avatar
            existing_cookie.is_active = True
            existing_cookie.is_valid = True
            existing_cookie.last_checked = datetime.utcnow()
            # 保留原有的 run_start_time、total_run_seconds 等时间统计
            # 如果之前已失效，重新设置开始时间（优先使用用户提供的 filled_at）
            if not existing_cookie.run_start_time:
                existing_cookie.run_start_time = filled_at_dt if filled_at_dt else datetime.utcnow()
                logger.info(f"Cookie 之前已失效，重新开始计时 (start_time={existing_cookie.run_start_time})")
            
            cookie = existing_cookie
        else:
            # 新用户的Cookie：创建新记录，重新开始计时
            logger.info(f"检测到新用户 {user_id} 的Cookie，重新开始计时")
            
            # 保存新 Cookie
            cookie = Cookie(
                user_id=user_id,
                nickname=nickname,
                avatar=avatar,
                is_active=True,
                is_valid=True,
                last_checked=datetime.utcnow(),
                run_start_time=filled_at_dt if filled_at_dt else datetime.utcnow(),
                total_run_seconds=0,
                last_valid_duration=0,
            )
            cookie.set_cookie_str(cookie_str)
            
            db.session.add(cookie)
        
        db.session.commit()

        # 清理历史同步错误，避免旧错误反复触发 Cookie 失效提示
        reset_account_errors()
        
        crypto = get_crypto()
        run_info = cookie.get_run_info()
        
        return success_response(
            data={
                'user_id': user_id,
                'nickname': nickname,
                'avatar': avatar,
                'is_secure': crypto.is_secure,
                'run_info': run_info,
                'transport_encrypted': True,
            },
            message='Cookie 添加成功（加密传输）'
        )
        
    except Exception as e:
        logger.error(f"Cookie validation error: {e}")
        return ApiResponse.error(f'Cookie 验证失败: {str(e)}', 400, 'VALIDATION_FAILED')


def cleanup_duplicate_cookies(keep_count: int = 5) -> int:
    """
    清理同一用户的重复 Cookie 记录
    每个用户只保留最近的 keep_count 条记录
    
    Args:
        keep_count: 每个用户保留的最大记录数
        
    Returns:
        删除的记录数
    """
    try:
        from sqlalchemy import func
        
        # 获取所有用户ID
        user_ids = db.session.query(Cookie.user_id).filter(
            Cookie.user_id.isnot(None),
            Cookie.user_id != ''
        ).distinct().all()
        
        deleted_count = 0
        for (user_id,) in user_ids:
            # 获取该用户的所有 Cookie，按更新时间降序
            user_cookies = Cookie.query.filter_by(user_id=user_id).order_by(
                Cookie.updated_at.desc()
            ).all()
            
            # 如果超过保留数量，删除旧的
            if len(user_cookies) > keep_count:
                cookies_to_delete = user_cookies[keep_count:]
                for cookie in cookies_to_delete:
                    # 不删除激活的 Cookie
                    if not cookie.is_active:
                        db.session.delete(cookie)
                        deleted_count += 1
        
        if deleted_count > 0:
            db.session.commit()
            logger.info(f"清理了 {deleted_count} 条重复的 Cookie 历史记录")
        
        return deleted_count
    except Exception as e:
        db.session.rollback()
        logger.error(f"清理 Cookie 历史记录失败: {e}")
        return 0


@auth_bp.route('/cookie/history', methods=['GET'])
def get_cookie_history():
    """
    获取 Cookie 历史记录
    返回最近的 Cookie 列表（不包含敏感数据）
    同时自动清理重复记录
    """
    # 自动清理重复记录（每个用户只保留最近5条）
    cleanup_duplicate_cookies(keep_count=5)
    
    cookies = Cookie.query.order_by(Cookie.updated_at.desc()).limit(10).all()
    
    return success_response({
        'cookies': [c.to_dict() for c in cookies]
    })


@auth_bp.route('/cookie/reactivate/<int:cookie_id>', methods=['POST'])
def reactivate_cookie(cookie_id):
    """
    重新激活历史 Cookie
    """
    cookie = Cookie.query.get(cookie_id)
    
    if not cookie:
        return ApiResponse.error('Cookie 不存在', 404, 'NOT_FOUND')
    
    # 验证 Cookie 是否仍然有效
    is_valid, _ = validate_cookie_if_needed(cookie, force=True)
    
    if not is_valid:
        return success_response({
            'success': False,
            'message': 'Cookie 已失效，无法重新激活',
            'run_info': cookie.get_run_info(),
        })
    
    # 将其他 Cookie 设为非激活
    Cookie.query.update({'is_active': False})
    cookie.is_active = True
    db.session.commit()
    
    return success_response({
        'success': True,
        'message': 'Cookie 已重新激活',
        'user_id': cookie.user_id,
        'nickname': cookie.nickname,
        'avatar': cookie.avatar,
        'run_info': cookie.get_run_info(),
    })


@auth_bp.route('/cookie/debug', methods=['GET'])
def debug_cookie():
    """
    调试接口：返回 Cookie 验证时 API 返回的原始数据
    仅用于调试，生产环境应禁用
    """
    cookie = Cookie.query.filter_by(is_active=True).first()
    
    if not cookie:
        return success_response({
            'error': '没有激活的 Cookie'
        })
    
    cookie_str = cookie.get_cookie_str()
    if not cookie_str:
        return success_response({
            'error': 'Cookie 字符串为空'
        })
    
    try:
        from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        
        # 获取 v1 接口数据
        success1, msg1, res1 = xhs_apis.get_user_self_info(cookie_str)
        
        # 获取 v2 接口数据
        success2, msg2, res2 = xhs_apis.get_user_self_info2(cookie_str)
        
        return success_response({
            'database_info': {
                'id': cookie.id,
                'user_id': cookie.user_id,
                'nickname': cookie.nickname,
                'avatar': cookie.avatar,
                'is_active': cookie.is_active,
                'is_valid': cookie.is_valid,
                'last_checked': (cookie.last_checked.isoformat() + 'Z') if cookie.last_checked else None,
                'run_info': cookie.get_run_info(),
            },
            'selfinfo_v1': {
                'success': success1,
                'msg': msg1,
                'data': res1.get('data') if res1 else None,
            },
            'selfinfo_v2': {
                'success': success2,
                'msg': msg2,
                'data': res2.get('data') if res2 else None,
            }
        })
    except Exception as e:
        return success_response({
            'error': str(e)
        })

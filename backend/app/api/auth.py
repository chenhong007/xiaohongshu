"""
认证相关 API
"""
from flask import Blueprint, request, current_app
from datetime import datetime

from ..extensions import db
from ..models import Cookie
from ..utils.responses import ApiResponse, success_response
from ..utils.validators import validate_cookie_str
from ..utils.crypto import encrypt_cookie, decrypt_cookie, get_crypto
from ..utils.logger import get_logger

auth_bp = Blueprint('auth', __name__)
logger = get_logger('auth')

# Cookie 验证间隔（秒）- 5分钟内不重复验证
COOKIE_CHECK_INTERVAL = 300


def get_active_cookie():
    """
    获取当前激活的 Cookie（已解密）
    
    Returns:
        Cookie 字符串或空字符串
    """
    cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if cookie:
        return cookie.get_cookie_str()
    # 如果数据库没有，尝试从配置获取
    return current_app.config.get('XHS_COOKIES', '')


def invalidate_cookie(cookie_id=None):
    """
    标记 Cookie 失效
    用于 API 调用失败时自动失效
    同时记录运行时长
    """
    if cookie_id:
        cookie = Cookie.query.get(cookie_id)
    else:
        cookie = Cookie.query.filter_by(is_active=True).first()
    
    if cookie:
        # 停止运行计时器并记录时长
        cookie.stop_run_timer()
        cookie.is_valid = False
        cookie.last_checked = datetime.utcnow()
        db.session.commit()
        logger.info(f"Cookie {cookie.id} 已标记失效，运行时长: {cookie.last_valid_duration}秒")
        return True
    return False


def get_recent_valid_cookie():
    """
    获取最近的有效历史 Cookie
    优先使用最近添加且有效的 Cookie
    """
    # 首先检查当前激活的
    active_cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if active_cookie:
        return active_cookie
    
    # 没有激活的，查找最近的有效 Cookie
    recent_cookie = Cookie.query.filter_by(is_valid=True).order_by(Cookie.updated_at.desc()).first()
    if recent_cookie:
        # 将其设为激活
        Cookie.query.update({'is_active': False})
        recent_cookie.is_active = True
        db.session.commit()
        logger.info(f"自动激活历史 Cookie: {recent_cookie.id}")
        return recent_cookie
    
    return None


def should_validate_cookie(cookie):
    """
    判断是否需要验证 Cookie
    基于上次检查时间，避免频繁验证
    """
    if not cookie.last_checked:
        return True
    
    time_since_check = datetime.utcnow() - cookie.last_checked
    return time_since_check.total_seconds() > COOKIE_CHECK_INTERVAL


def validate_cookie_if_needed(cookie, force=False):
    """
    按需验证 Cookie
    返回: (is_valid, user_info_dict or None)
    """
    # 如果不需要验证且标记为有效，直接返回
    if not force and not should_validate_cookie(cookie) and cookie.is_valid:
        return True, None
    
    # 记录之前的状态
    was_valid = cookie.is_valid
    
    try:
        from apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        
        # 获取解密后的 Cookie
        cookie_str = cookie.get_cookie_str()
        
        # 先尝试 v1 selfinfo 接口
        success, msg, res = xhs_apis.get_user_self_info(cookie_str)
        logger.info(f"[validate_cookie] selfinfo v1 返回: success={success}, msg={msg}")
        
        # 如果 v1 成功，再尝试 v2 接口获取更详细的信息
        res2_data = None
        if success:
            try:
                success2, msg2, res2 = xhs_apis.get_user_self_info2(cookie_str)
                logger.info(f"[validate_cookie] selfinfo v2 返回: success={success2}, msg={msg2}")
                if success2 and res2.get('data'):
                    res2_data = res2['data']
                    logger.info(f"[validate_cookie] v2 数据键: {list(res2_data.keys()) if isinstance(res2_data, dict) else type(res2_data)}")
            except Exception as e:
                logger.warning(f"[validate_cookie] v2 接口调用失败: {e}")
        
        # 更新验证状态
        cookie.last_checked = datetime.utcnow()
        cookie.is_valid = success
        
        if success and res.get('data'):
            # 验证成功，启动运行计时器（如果还没有启动）
            cookie.start_run_timer()
            
            # 优先使用 v2 数据（如果有），否则使用 v1 数据
            data_to_use = res2_data if res2_data else res['data']
            logger.info(f"[validate_cookie] 使用{'v2' if res2_data else 'v1'}数据提取用户信息")
            
            # 更新用户信息（可能有变化）
            user_id, nickname, avatar = extract_user_info(data_to_use)
            if user_id:
                cookie.user_id = user_id
            if nickname and nickname != '未知用户':
                cookie.nickname = nickname
            if avatar:
                cookie.avatar = avatar
        elif was_valid and not success:
            # Cookie 从有效变为无效，停止计时器
            cookie.stop_run_timer()
            logger.info(f"Cookie {cookie.id} 失效，运行时长: {cookie.last_valid_duration}秒")
        
        db.session.commit()
        return success, res.get('data') if success else None
        
    except Exception as e:
        logger.error(f"Cookie validation error: {e}")
        cookie.last_checked = datetime.utcnow()
        if was_valid:
            cookie.stop_run_timer()
        cookie.is_valid = False
        db.session.commit()
        return False, None


def extract_user_info(res_data):
    """从 API 响应中提取用户信息"""
    if not res_data:
        return None, None, None
    
    # 调试：打印 API 返回的原始数据结构
    logger.info(f"[extract_user_info] 原始数据键: {list(res_data.keys()) if isinstance(res_data, dict) else type(res_data)}")
    
    # 尝试获取 basic_info，如果不存在则使用 data 本身
    basic_info = res_data.get('basic_info', res_data)
    
    # 调试：打印 basic_info 的键
    if basic_info and basic_info != res_data:
        logger.info(f"[extract_user_info] basic_info 键: {list(basic_info.keys()) if isinstance(basic_info, dict) else type(basic_info)}")
    
    # 获取昵称（尝试多个字段）
    # selfinfo 接口可能返回 'nickname' 直接在根级别
    nickname = (basic_info.get('nickname') or 
                res_data.get('nickname') or 
                res_data.get('nick_name') or
                '未知用户')
    
    # 获取头像（尝试多个字段）
    # selfinfo 接口可能使用 'headPhoto' 或 'head_photo' 或 'image'
    avatar = (basic_info.get('imageb') or basic_info.get('images') or 
              basic_info.get('avatar') or basic_info.get('head_photo') or
              basic_info.get('headPhoto') or
              res_data.get('imageb') or res_data.get('images') or 
              res_data.get('avatar') or res_data.get('head_photo') or 
              res_data.get('headPhoto') or
              res_data.get('image') or '')
    
    # 获取用户ID（尝试多个字段）
    # selfinfo 接口可能使用 'userId' 或 'user_id'
    user_id = (basic_info.get('user_id') or basic_info.get('userId') or
               basic_info.get('red_id') or basic_info.get('redId') or
               res_data.get('user_id') or res_data.get('userId') or
               res_data.get('red_id') or res_data.get('redId') or '')
    
    logger.info(f"[extract_user_info] 提取结果: user_id={user_id}, nickname={nickname}, avatar={avatar[:50] if avatar else 'None'}...")
    
    return user_id, nickname, avatar


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
    
    # 优先使用最近的有效历史 Cookie
    cookie = get_recent_valid_cookie()
    
    if not cookie:
        # 没有有效 Cookie，尝试获取任何激活的 Cookie（可能已失效）
        cookie = Cookie.query.filter_by(is_active=True).first()
    
    if cookie:
        # 按需验证 Cookie（基于时间间隔或强制验证）
        if force_check or should_validate_cookie(cookie):
            is_valid, _ = validate_cookie_if_needed(cookie, force=force_check)
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
                'last_checked': cookie.last_checked.isoformat() if cookie.last_checked else None,
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
            from apis.xhs_pc_apis import XHS_Apis
            xhs_apis = XHS_Apis()
            success, msg, res = xhs_apis.get_user_self_info(cookies_str)
            
            if success and res.get('data'):
                user_id, nickname, avatar = extract_user_info(res['data'])
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
    
    # 验证 Cookie 格式
    is_valid, error_msg = validate_cookie_str(cookie_str)
    if not is_valid:
        return ApiResponse.validation_error(error_msg)
    
    # 验证 Cookie 有效性
    try:
        from apis.xhs_pc_apis import XHS_Apis
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
        
        # 将之前的 Cookie 设为非激活
        Cookie.query.update({'is_active': False})
        
        # 保存新 Cookie（加密存储）
        cookie = Cookie(
            user_id=user_id,
            nickname=nickname,
            avatar=avatar,
            is_active=True,
            is_valid=True,
            last_checked=datetime.utcnow()
        )
        # 使用加密方法设置 Cookie
        cookie.set_cookie_str(cookie_str)
        
        # 启动运行计时器
        cookie.start_run_timer()
        
        db.session.add(cookie)
        db.session.commit()
        
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
        'last_checked': cookie.last_checked.isoformat() if cookie.last_checked else None
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
        from apis.xhs_pc_apis import XHS_Apis
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
        
        # 将之前的 Cookie 设为非激活
        Cookie.query.update({'is_active': False})
        
        # 保存新 Cookie
        cookie = Cookie(
            user_id=user_id,
            nickname=nickname,
            avatar=avatar,
            is_active=True,
            is_valid=True,
            last_checked=datetime.utcnow()
        )
        cookie.set_cookie_str(cookie_str)
        cookie.start_run_timer()
        
        db.session.add(cookie)
        db.session.commit()
        
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


@auth_bp.route('/cookie/history', methods=['GET'])
def get_cookie_history():
    """
    获取 Cookie 历史记录
    返回最近的 Cookie 列表（不包含敏感数据）
    """
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
        from apis.xhs_pc_apis import XHS_Apis
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
                'last_checked': cookie.last_checked.isoformat() if cookie.last_checked else None,
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

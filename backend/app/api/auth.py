"""
认证相关 API
"""
from flask import Blueprint, jsonify, request, current_app
from datetime import datetime, timedelta

from ..extensions import db
from ..models import Cookie

auth_bp = Blueprint('auth', __name__)

# Cookie 验证间隔（秒）- 5分钟内不重复验证
COOKIE_CHECK_INTERVAL = 300


def get_active_cookie():
    """获取当前激活的 Cookie"""
    cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if cookie:
        return cookie.cookie_str
    # 如果数据库没有，尝试从配置获取
    return current_app.config.get('XHS_COOKIES', '')


def invalidate_cookie(cookie_id=None):
    """
    标记 Cookie 失效
    用于 API 调用失败时自动失效
    """
    if cookie_id:
        cookie = Cookie.query.get(cookie_id)
    else:
        cookie = Cookie.query.filter_by(is_active=True).first()
    
    if cookie:
        cookie.is_valid = False
        cookie.last_checked = datetime.utcnow()
        db.session.commit()
        return True
    return False


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
    
    try:
        from apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        success, msg, res = xhs_apis.get_user_self_info(cookie.cookie_str)
        
        # 更新验证状态
        cookie.last_checked = datetime.utcnow()
        cookie.is_valid = success
        
        if success and res.get('data'):
            # 更新用户信息（可能有变化）
            user_id, nickname, avatar = extract_user_info(res['data'])
            if user_id:
                cookie.user_id = user_id
            if nickname:
                cookie.nickname = nickname
            if avatar:
                cookie.avatar = avatar
        
        db.session.commit()
        return success, res.get('data') if success else None
        
    except Exception as e:
        current_app.logger.error(f"Cookie validation error: {e}")
        cookie.last_checked = datetime.utcnow()
        cookie.is_valid = False
        db.session.commit()
        return False, None


def extract_user_info(res_data):
    """从 API 响应中提取用户信息"""
    if not res_data:
        return None, None, None
    
    # 尝试获取 basic_info，如果不存在则使用 data 本身
    basic_info = res_data.get('basic_info', res_data)
    
    # 获取昵称（尝试多个字段）
    nickname = basic_info.get('nickname') or res_data.get('nickname') or '未知用户'
    
    # 获取头像（尝试多个字段：imageb, images, avatar, head_photo, image）
    avatar = (basic_info.get('imageb') or basic_info.get('images') or 
              basic_info.get('avatar') or basic_info.get('head_photo') or
              res_data.get('imageb') or res_data.get('images') or 
              res_data.get('avatar') or res_data.get('head_photo') or 
              res_data.get('image') or '')
    
    # 获取用户ID（尝试多个字段）
    user_id = (basic_info.get('user_id') or basic_info.get('red_id') or 
               res_data.get('user_id') or res_data.get('red_id') or '')
    
    return user_id, nickname, avatar


@auth_bp.route('/user/me', methods=['GET'])
def get_current_user():
    """
    获取当前登录用户信息
    支持参数:
    - force_check: 是否强制验证 Cookie（默认 false）
    """
    force_check = request.args.get('force_check', 'false').lower() == 'true'
    
    cookie = Cookie.query.filter_by(is_active=True).first()
    
    if cookie:
        # 按需验证 Cookie（基于时间间隔或强制验证）
        if force_check or should_validate_cookie(cookie):
            is_valid, _ = validate_cookie_if_needed(cookie, force=force_check)
            if not is_valid:
                return jsonify({
                    'is_connected': False,
                    'was_connected': True,  # 标记之前是连接状态
                    'message': 'Cookie 已失效，请重新登录'
                })
        
        # Cookie 有效，返回用户信息
        if cookie.is_valid:
            return jsonify({
                'is_connected': True,
                'user_id': cookie.user_id,
                'nickname': cookie.nickname,
                'avatar': cookie.avatar,
                'last_checked': cookie.last_checked.isoformat() if cookie.last_checked else None,
            })
        else:
            return jsonify({
                'is_connected': False,
                'was_connected': True,
                'message': 'Cookie 已失效，请重新登录'
            })
    
    # 检查配置中的 Cookie
    cookies_str = current_app.config.get('XHS_COOKIES', '')
    if cookies_str:
        # 尝试验证 Cookie 并获取用户信息
        try:
            from apis.xhs_pc_apis import XHS_Apis
            xhs_apis = XHS_Apis()
            success, msg, res = xhs_apis.get_user_self_info(cookies_str)
            
            if success and res.get('data'):
                user_id, nickname, avatar = extract_user_info(res['data'])
                return jsonify({
                    'is_connected': True,
                    'user_id': user_id,
                    'nickname': nickname,
                    'avatar': avatar,
                })
        except Exception as e:
            current_app.logger.error(f"Failed to validate cookie: {e}")
    
    return jsonify({
        'is_connected': False,
        'message': '未连接小红书账号'
    })


@auth_bp.route('/login', methods=['POST'])
def login():
    """
    触发登录流程
    可以扩展为打开浏览器自动登录获取 Cookie
    """
    # 这里暂时返回提示信息，实际可以集成自动化登录脚本
    return jsonify({
        'success': True,
        'message': '请手动添加 Cookie 或使用自动登录脚本'
    })


@auth_bp.route('/cookie/manual', methods=['POST'])
def manual_cookie():
    """手动添加 Cookie"""
    data = request.json
    cookie_str = data.get('cookies', '')
    
    if not cookie_str:
        return jsonify({'error': 'Cookie 不能为空'}), 400
    
    # 验证 Cookie 有效性
    try:
        from apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        success, msg, res = xhs_apis.get_user_self_info(cookie_str)
        
        if not success:
            return jsonify({'error': f'Cookie 无效: {msg}'}), 400
        
        # 使用统一的提取函数
        user_id, nickname, avatar = extract_user_info(res.get('data', {}))
        
        current_app.logger.info(f"Extracted user info: user_id={user_id}, nickname={nickname}, avatar={avatar[:50] if avatar else 'None'}...")
        
        # 将之前的 Cookie 设为非激活
        Cookie.query.update({'is_active': False})
        
        # 保存新 Cookie
        cookie = Cookie(
            cookie_str=cookie_str,
            user_id=user_id,
            nickname=nickname,
            avatar=avatar,
            is_active=True,
            is_valid=True,
            last_checked=datetime.utcnow()
        )
        db.session.add(cookie)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'user_id': user_id,
                'nickname': nickname,
                'avatar': avatar,
            }
        })
        
    except Exception as e:
        current_app.logger.error(f"Cookie validation error: {e}")
        return jsonify({'error': f'Cookie 验证失败: {str(e)}'}), 400


@auth_bp.route('/cookie/check', methods=['POST'])
def check_cookie():
    """检查当前 Cookie 是否有效（强制验证）"""
    cookie = Cookie.query.filter_by(is_active=True).first()
    
    if not cookie:
        return jsonify({
            'is_valid': False,
            'message': '没有激活的 Cookie'
        })
    
    # 强制验证
    is_valid, _ = validate_cookie_if_needed(cookie, force=True)
    
    return jsonify({
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
    return jsonify({
        'success': success,
        'message': 'Cookie 已标记失效' if success else '没有激活的 Cookie'
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """登出（停用当前 Cookie）"""
    Cookie.query.filter_by(is_active=True).update({'is_active': False})
    db.session.commit()
    return jsonify({'success': True})


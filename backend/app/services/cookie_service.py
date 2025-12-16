"""
Cookie 验证服务 - 统一的 Cookie 管理和验证逻辑

所有涉及 Cookie 验证的场景都应该使用这个服务，确保逻辑一致性：
- 搜索用户/笔记
- 获取当前用户状态
- 同步数据前的验证
- 刷新 Cookie 状态
"""
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from flask import current_app

from ..models import Cookie
from ..extensions import db
from ..utils.logger import get_logger

logger = get_logger('cookie_service')

# Cookie 验证间隔（秒）- 5分钟内不重复验证
COOKIE_CHECK_INTERVAL = 300


class CookieService:
    """统一的 Cookie 服务类"""
    
    @staticmethod
    def get_active_cookie() -> Optional[Cookie]:
        """
        获取当前激活的 Cookie 对象
        
        Returns:
            Cookie 对象或 None
        """
        return Cookie.query.filter_by(is_active=True).first()
    
    @staticmethod
    def get_valid_cookie() -> Optional[Cookie]:
        """
        获取当前激活且有效的 Cookie 对象
        
        Returns:
            Cookie 对象或 None
        """
        return Cookie.query.filter_by(is_active=True, is_valid=True).first()
    
    @staticmethod
    def get_recent_valid_cookie() -> Optional[Cookie]:
        """
        获取最近的有效历史 Cookie
        优先使用最近添加且有效的 Cookie
        
        Returns:
            Cookie 对象或 None
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
    
    @staticmethod
    def should_validate(cookie: Cookie) -> bool:
        """
        判断是否需要验证 Cookie
        基于上次检查时间，避免频繁验证
        
        Args:
            cookie: Cookie 对象
            
        Returns:
            是否需要验证
        """
        if not cookie.last_checked:
            return True
        
        time_since_check = datetime.utcnow() - cookie.last_checked
        return time_since_check.total_seconds() > COOKIE_CHECK_INTERVAL
    
    @staticmethod
    def _do_validate(cookie: Cookie) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        实际执行 Cookie 验证（调用小红书 API）
        
        Args:
            cookie: Cookie 对象
            
        Returns:
            (is_valid, user_info_dict or None)
        """
        from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
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
        
        if success and res.get('data'):
            # 优先使用 v2 数据（如果有），否则使用 v1 数据
            data_to_use = res2_data if res2_data else res['data']
            return True, data_to_use
        
        return success, None
    
    @staticmethod
    def _extract_user_info(res_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        从 API 响应中提取用户信息
        
        Args:
            res_data: API 响应数据
            
        Returns:
            (user_id, nickname, avatar)
        """
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
        nickname = (basic_info.get('nickname') or 
                   basic_info.get('nick_name') or 
                   basic_info.get('name') or 
                   res_data.get('nickname') or
                   res_data.get('nick_name') or
                   res_data.get('name'))
        
        # 获取用户 ID（尝试多个字段）
        user_id = (basic_info.get('user_id') or 
                  basic_info.get('userid') or 
                  basic_info.get('id') or
                  basic_info.get('red_id') or
                  res_data.get('user_id') or
                  res_data.get('userid') or
                  res_data.get('id') or
                  res_data.get('red_id'))
        
        # 获取头像（尝试多个字段）
        avatar = (basic_info.get('image') or 
                 basic_info.get('images') or
                 basic_info.get('avatar') or
                 basic_info.get('headPhoto') or
                 res_data.get('image') or
                 res_data.get('images') or
                 res_data.get('avatar') or
                 res_data.get('headPhoto'))
        
        logger.info(f"[extract_user_info] 提取结果: user_id={user_id}, nickname={nickname}, avatar={'有' if avatar else '无'}")
        
        return user_id, nickname, avatar
    
    @staticmethod
    def validate_if_needed(cookie: Cookie, force: bool = False) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        按需验证 Cookie（核心验证方法）
        
        如果 Cookie 被标记为无效，会尝试重新验证。
        如果验证成功，会自动恢复 Cookie 的有效状态。
        验证结果会立即同步到数据库。
        
        Args:
            cookie: Cookie 对象
            force: 是否强制验证（忽略时间间隔）
            
        Returns:
            (is_valid, user_info_dict or None)
        """
        # 如果不需要验证且标记为有效，直接返回
        if not force and not CookieService.should_validate(cookie) and cookie.is_valid:
            return True, None
        
        # 记录之前的状态
        was_valid = cookie.is_valid
        logger.info(f"[validate_cookie] 开始验证 Cookie {cookie.id}，当前状态: is_valid={was_valid}, force={force}")
        
        try:
            success, user_data = CookieService._do_validate(cookie)
            
            # 更新验证状态（无论成功与否都要更新）
            cookie.last_checked = datetime.utcnow()
            cookie.is_valid = success
            
            if success:
                # 验证成功，启动运行计时器（如果还没有启动）
                cookie.start_run_timer()
                
                if user_data:
                    logger.info(f"[validate_cookie] 验证成功，提取用户信息")
                    
                    # 更新用户信息（可能有变化）
                    user_id, nickname, avatar = CookieService._extract_user_info(user_data)
                    if user_id:
                        cookie.user_id = user_id
                    if nickname and nickname != '未知用户':
                        cookie.nickname = nickname
                    if avatar:
                        cookie.avatar = avatar
                else:
                    logger.info(f"[validate_cookie] 验证成功，但无用户数据")
                
                # 如果之前是无效的，现在恢复了
                if not was_valid:
                    logger.info(f"Cookie {cookie.id} 重新验证成功，已恢复有效状态")
                    
            else:
                # 验证失败
                if was_valid:
                    # Cookie 从有效变为无效，停止计时器
                    cookie.stop_run_timer()
                    logger.info(f"Cookie {cookie.id} 验证失败，已标记失效，运行时长: {cookie.last_valid_duration}秒")
                else:
                    logger.info(f"Cookie {cookie.id} 验证失败，保持失效状态")
            
            # 立即同步到数据库
            db.session.commit()
            logger.debug(f"[validate_cookie] Cookie {cookie.id} 状态已同步到数据库: is_valid={cookie.is_valid}")
            
            return success, user_data
            
        except Exception as e:
            logger.error(f"Cookie validation error: {e}")
            cookie.last_checked = datetime.utcnow()
            if was_valid:
                cookie.stop_run_timer()
            cookie.is_valid = False
            
            # 异常情况也要同步到数据库
            try:
                db.session.commit()
                logger.debug(f"[validate_cookie] Cookie {cookie.id} 异常状态已同步到数据库")
            except Exception as commit_error:
                logger.error(f"[validate_cookie] 同步数据库失败: {commit_error}")
                db.session.rollback()
            
            return False, None
    
    @staticmethod
    def invalidate(cookie_id: Optional[int] = None) -> bool:
        """
        标记 Cookie 失效
        用于 API 调用失败时自动失效
        同时记录运行时长
        
        Args:
            cookie_id: 指定的 Cookie ID，如果为 None 则使用当前激活的
            
        Returns:
            是否成功标记失效
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
    
    @staticmethod
    def check_valid() -> Tuple[bool, str]:
        """
        检查当前 Cookie 是否有效（带自动恢复）
        
        这是最常用的验证方法，会：
        1. 检查是否有激活的 Cookie
        2. 如果 Cookie 被标记为无效，尝试重新验证
        3. 如果验证成功，自动恢复有效状态
        4. 验证结果会立即同步到数据库
        
        Returns:
            (is_valid, error_message)
        """
        cookie = CookieService.get_active_cookie()
        if not cookie:
            logger.debug("[check_valid] 没有激活的 Cookie")
            return False, '未配置 Cookie，请先登录'
        
        # 如果 Cookie 被标记为无效，尝试重新验证
        if not cookie.is_valid:
            logger.info(f"[check_valid] Cookie {cookie.id} 被标记为无效，尝试重新验证...")
            is_valid, _ = CookieService.validate_if_needed(cookie, force=True)
            # validate_if_needed 内部已经同步到数据库
            if is_valid:
                logger.info(f"[check_valid] Cookie {cookie.id} 重新验证成功，状态已同步")
                return True, ''
            else:
                logger.info(f"[check_valid] Cookie {cookie.id} 验证失败，状态已同步")
                return False, 'Cookie 已失效，请重新登录更新 Cookie'
        
        # Cookie 标记为有效，检查是否需要定期验证
        if CookieService.should_validate(cookie):
            logger.debug(f"[check_valid] Cookie {cookie.id} 需要定期验证")
            is_valid, _ = CookieService.validate_if_needed(cookie, force=False)
            # validate_if_needed 内部已经同步到数据库
            if not is_valid:
                logger.info(f"[check_valid] Cookie {cookie.id} 定期验证失败，状态已同步")
                return False, 'Cookie 已失效，请重新登录更新 Cookie'
        
        logger.debug(f"[check_valid] Cookie {cookie.id} 有效")
        return True, ''
    
    @staticmethod
    def get_cookie_str() -> str:
        """
        获取有效的解密后 Cookie 字符串（带自动恢复）
        
        这是获取 Cookie 字符串的统一方法，会：
        1. 优先获取有效的 Cookie
        2. 如果没有有效 Cookie，尝试验证被标记为无效的 Cookie
        3. 如果验证成功，返回该 Cookie 字符串
        4. 验证结果会立即同步到数据库
        
        Returns:
            Cookie 字符串，如果没有有效 Cookie 则返回空字符串
        """
        # 首先尝试获取有效的 Cookie
        cookie = CookieService.get_valid_cookie()
        if cookie:
            logger.debug(f"[get_cookie_str] 使用有效 Cookie {cookie.id}")
            return cookie.get_cookie_str()
        
        # 如果没有有效 Cookie，尝试获取被标记为无效的激活 Cookie
        invalid_cookie = Cookie.query.filter_by(is_active=True, is_valid=False).first()
        if invalid_cookie:
            # 尝试重新验证这个 Cookie
            logger.info(f"[get_cookie_str] 没有有效 Cookie，尝试重新验证 Cookie {invalid_cookie.id}...")
            is_valid, _ = CookieService.validate_if_needed(invalid_cookie, force=True)
            # validate_if_needed 内部已经同步到数据库
            if is_valid:
                logger.info(f"[get_cookie_str] Cookie {invalid_cookie.id} 重新验证成功，状态已同步")
                return invalid_cookie.get_cookie_str()
            else:
                logger.info(f"[get_cookie_str] Cookie {invalid_cookie.id} 验证失败，状态已同步")
        
        # 尝试从配置获取
        config_cookie = current_app.config.get('XHS_COOKIES', '')
        if config_cookie:
            logger.debug("[get_cookie_str] 使用配置中的 Cookie")
        else:
            logger.debug("[get_cookie_str] 没有可用的 Cookie")
        return config_cookie
    
    @staticmethod
    def get_status() -> Dict[str, Any]:
        """
        获取当前 Cookie 状态信息
        
        Returns:
            包含 Cookie 状态的字典
        """
        cookie = CookieService.get_active_cookie()
        if not cookie:
            return {
                'has_cookie': False,
                'is_valid': False,
                'message': '未配置 Cookie'
            }
        
        return {
            'has_cookie': True,
            'is_valid': cookie.is_valid,
            'user_id': cookie.user_id,
            'nickname': cookie.nickname,
            'avatar': cookie.avatar,
            'last_checked': cookie.last_checked.isoformat() if cookie.last_checked else None,
            'run_info': cookie.get_run_info() if hasattr(cookie, 'get_run_info') else None,
        }


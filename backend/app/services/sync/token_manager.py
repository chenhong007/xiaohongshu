"""
XsecTokenManager - 小红书 xsec_token 统一管理

功能：
- 用户级别 token 缓存，避免重复获取
- 自动刷新过期 token
- 统一的 URL 构建方法
- 预防性 token 刷新策略
"""
import time
import threading
from typing import Any, Dict, Optional, Tuple
from dataclasses import dataclass

from ...utils.logger import get_logger

logger = get_logger('token_manager')


@dataclass
class TokenInfo:
    """Token 缓存信息"""
    token: str
    fetch_time: float  # Unix timestamp
    use_count: int = 0  # 使用次数，用于判断是否需要预防性刷新


@dataclass
class UserInfoCache:
    """用户信息缓存，避免重复调用 get_user_info API"""
    user_id: str
    nickname: Optional[str] = None
    avatar: Optional[str] = None
    desc: Optional[str] = None
    fans: Optional[int] = None
    follows: Optional[int] = None
    interaction: Optional[int] = None
    fetch_time: float = 0.0  # Unix timestamp
    raw_data: Optional[Dict] = None  # 原始返回数据，供其他用途使用


class XsecTokenManager:
    """xsec_token 统一管理器
    
    统一管理用户和笔记的 xsec_token，提供：
    - 缓存机制，避免重复请求
    - 自动过期检测和刷新
    - 预防性刷新策略（每 N 次使用后主动刷新）
    - 统一的 URL 构建接口
    
    使用示例:
        token_mgr = XsecTokenManager(xhs_apis, cookie_str)
        
        # 获取用户 token（自动缓存）
        token = token_mgr.get_user_token(user_id)
        
        # 构建 URL
        user_url = token_mgr.build_user_url(user_id)
        note_url = token_mgr.build_note_url(note_id, note_token)
    """
    
    # Token 过期时间（秒）- 保守估计，实际可能更长
    TOKEN_EXPIRE_SECONDS = 600  # 10 分钟
    
    # 预防性刷新阈值 - 使用次数超过此值后主动刷新
    PREEMPTIVE_REFRESH_THRESHOLD = 50
    
    # URL 模板
    USER_URL_TEMPLATE = "https://www.xiaohongshu.com/user/profile/{user_id}"
    NOTE_URL_TEMPLATE = "https://www.xiaohongshu.com/explore/{note_id}"
    
    # 用户信息缓存过期时间（秒）- 同步期间通常不需要刷新
    USER_INFO_EXPIRE_SECONDS = 3600  # 1 小时
    
    def __init__(self, xhs_apis, cookie_str: str):
        """初始化 Token 管理器
        
        Args:
            xhs_apis: XHS_Apis 实例，用于调用小红书 API
            cookie_str: Cookie 字符串，用于 API 认证
        """
        self._xhs_apis = xhs_apis
        self._cookie_str = cookie_str
        self._token_cache: Dict[str, TokenInfo] = {}  # user_id -> TokenInfo
        self._user_info_cache: Dict[str, UserInfoCache] = {}  # user_id -> UserInfoCache
        self._lock = threading.Lock()
    
    def get_user_token(self, user_id: str, force_refresh: bool = False) -> str:
        """获取用户的 xsec_token（带缓存）
        
        Args:
            user_id: 用户 ID
            force_refresh: 是否强制刷新（忽略缓存）
            
        Returns:
            xsec_token 字符串，获取失败返回空字符串
        """
        if not user_id:
            return ''
        
        with self._lock:
            # 检查缓存
            if not force_refresh and user_id in self._token_cache:
                token_info = self._token_cache[user_id]
                
                # 检查是否过期
                if self._is_token_valid(token_info):
                    token_info.use_count += 1
                    
                    # 检查是否需要预防性刷新
                    if token_info.use_count >= self.PREEMPTIVE_REFRESH_THRESHOLD:
                        logger.debug(f"Token for user {user_id} used {token_info.use_count} times, preemptive refresh")
                        # 异步刷新，但先返回当前 token
                        threading.Thread(
                            target=self._refresh_token_async, 
                            args=(user_id,),
                            daemon=True
                        ).start()
                    
                    return token_info.token
                else:
                    logger.debug(f"Token for user {user_id} expired, refreshing...")
        
        # 缓存未命中或已过期，获取新 token
        return self.refresh_user_token(user_id)
    
    def refresh_user_token(self, user_id: str) -> str:
        """强制刷新用户的 xsec_token
        
        从主页推荐（homefeed）获取通用 xsec_token，这个 token 可以用于访问用户笔记列表。
        笔记详情的 xsec_token 应从用户笔记列表接口 /api/sns/web/v1/user_posted 返回的数据中获取。
        
        Args:
            user_id: 用户 ID
            
        Returns:
            新的 xsec_token，获取失败返回空字符串
        """
        if not user_id or not self._xhs_apis:
            return ''
        
        # 从主页推荐获取通用 xsec_token
        # 主页推荐返回的笔记中包含 xsec_token，这个 token 可以用于访问用户笔记列表
        token = self._get_token_from_homefeed()
        if token:
            with self._lock:
                self._token_cache[user_id] = TokenInfo(
                    token=token,
                    fetch_time=time.time(),
                    use_count=0
                )
            logger.debug(f"Fetched xsec_token for user {user_id} via homefeed")
            return token
        
        logger.warning(f"Failed to fetch xsec_token for user {user_id} from homefeed")
        return ''
    
    def _get_token_from_homefeed(self) -> str:
        """从主页推荐获取 xsec_token
        
        主页推荐返回的笔记中包含有效的 xsec_token，这是最可靠的获取方式。
        
        Returns:
            xsec_token 字符串，获取失败返回空字符串
        """
        try:
            # 获取主页推荐的笔记（只需要1个笔记即可获取 token）
            success, msg, res_json = self._xhs_apis.get_homefeed_recommend(
                category='homefeed_recommend',  # 推荐频道
                cursor_score='',
                refresh_type=1,  # 首次刷新
                note_index=0,
                cookies_str=self._cookie_str
            )
            
            if not success or not res_json:
                logger.warning(f"Failed to get homefeed for token refresh: {msg}")
                return ''
            
            # 从返回的笔记中提取 xsec_token
            data = res_json.get('data', {})
            items = data.get('items', [])
            
            if not items:
                # homefeed 也可能返回空 items（与笔记详情类似的问题）
                logger.warning(f"Homefeed returned empty items, data keys: {list(data.keys())}")
                return ''
            
            for item in items:
                # 尝试从笔记的不同位置获取 xsec_token
                xsec_token = (
                    item.get('xsec_token') or
                    item.get('note_card', {}).get('xsec_token') or
                    item.get('id', '') and self._extract_token_from_item(item)
                )
                if xsec_token:
                    logger.debug(f"Got xsec_token from homefeed item (len={len(xsec_token)})")
                    return xsec_token
            
            logger.warning(f"No xsec_token found in {len(items)} homefeed items")
            
        except Exception as e:
            logger.warning(f"Exception getting token from homefeed: {e}")
        
        return ''
    
    def _extract_token_from_item(self, item: Dict) -> str:
        """从推荐项中提取 xsec_token
        
        Args:
            item: 推荐项数据
            
        Returns:
            xsec_token 字符串
        """
        # 尝试多种可能的字段路径
        paths = [
            ('xsec_token',),
            ('note_card', 'xsec_token'),
            ('track_id',),  # 有时 track_id 可以作为 token
        ]
        
        for path in paths:
            value = item
            for key in path:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    value = None
                    break
            if value and isinstance(value, str) and len(value) > 10:
                return value
        
        return ''
    
    def _refresh_token_async(self, user_id: str) -> None:
        """异步刷新 token（用于预防性刷新）"""
        try:
            self.refresh_user_token(user_id)
        except Exception as e:
            logger.debug(f"Async token refresh failed for {user_id}: {e}")
    
    def _is_token_valid(self, token_info: TokenInfo) -> bool:
        """检查 token 是否有效（未过期）
        
        Args:
            token_info: Token 信息
            
        Returns:
            True 如果 token 有效
        """
        if not token_info or not token_info.token:
            return False
        
        elapsed = time.time() - token_info.fetch_time
        return elapsed < self.TOKEN_EXPIRE_SECONDS
    
    def get_cached_token(self, user_id: str) -> Optional[str]:
        """获取缓存的 token（不触发刷新）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            缓存的 token，不存在返回 None
        """
        with self._lock:
            token_info = self._token_cache.get(user_id)
            if token_info and self._is_token_valid(token_info):
                return token_info.token
        return None
    
    def set_token(self, user_id: str, token: str) -> None:
        """手动设置用户的 token（用于外部获取的 token）
        
        Args:
            user_id: 用户 ID
            token: xsec_token 值
        """
        if user_id and token:
            with self._lock:
                self._token_cache[user_id] = TokenInfo(
                    token=token,
                    fetch_time=time.time(),
                    use_count=0
                )
    
    def invalidate_token(self, user_id: str) -> None:
        """使指定用户的 token 失效
        
        Args:
            user_id: 用户 ID
        """
        with self._lock:
            if user_id in self._token_cache:
                del self._token_cache[user_id]
    
    def clear_cache(self) -> None:
        """清空所有 token 缓存"""
        with self._lock:
            self._token_cache.clear()
            self._user_info_cache.clear()
    
    # ==================== 用户信息缓存方法 ====================
    
    def get_user_info(self, user_id: str, force_refresh: bool = False) -> Optional[UserInfoCache]:
        """获取用户信息（带缓存）
        
        首次调用会请求 API 并缓存结果，后续调用直接返回缓存。
        这避免了在同步过程中重复调用 get_user_info API。
        
        Args:
            user_id: 用户 ID
            force_refresh: 是否强制刷新（忽略缓存）
            
        Returns:
            UserInfoCache 对象，获取失败返回 None
        """
        if not user_id:
            return None
        
        # 检查缓存
        if not force_refresh:
            with self._lock:
                cached = self._user_info_cache.get(user_id)
                if cached and self._is_user_info_valid(cached):
                    logger.debug(f"Using cached user info for {user_id}")
                    return cached
        
        # 缓存未命中或已过期，获取新数据
        return self._fetch_and_cache_user_info(user_id)
    
    def _is_user_info_valid(self, info: UserInfoCache) -> bool:
        """检查用户信息缓存是否有效"""
        if not info or not info.user_id:
            return False
        elapsed = time.time() - info.fetch_time
        return elapsed < self.USER_INFO_EXPIRE_SECONDS
    
    def _fetch_and_cache_user_info(self, user_id: str) -> Optional[UserInfoCache]:
        """从 API 获取用户信息并缓存
        
        Args:
            user_id: 用户 ID
            
        Returns:
            UserInfoCache 对象，获取失败返回 None
        """
        if not self._xhs_apis:
            return None
        
        try:
            success, msg, res = self._xhs_apis.get_user_info(user_id, self._cookie_str)
            
            if not success or not res:
                logger.warning(f"Failed to get user info for {user_id}: {msg}")
                return None
            
            user_data = res.get('data', {})
            if not user_data:
                return None
            
            # 解析用户信息
            basic_info = user_data.get('basic_info', {})
            
            # 解析互动数据
            fans = follows = interaction = None
            for item in user_data.get('interactions', []):
                item_type = item.get('type')
                if item_type == 'fans':
                    fans = item.get('count')
                elif item_type == 'follows':
                    follows = item.get('count')
                elif item_type == 'interaction':
                    interaction = item.get('count')
            
            # 创建缓存对象
            user_info = UserInfoCache(
                user_id=user_id,
                nickname=basic_info.get('nickname'),
                avatar=basic_info.get('images'),
                desc=basic_info.get('desc'),
                fans=fans,
                follows=follows,
                interaction=interaction,
                fetch_time=time.time(),
                raw_data=user_data
            )
            
            # 存入缓存
            with self._lock:
                self._user_info_cache[user_id] = user_info
            
            logger.debug(f"Fetched and cached user info for {user_id}")
            return user_info
            
        except Exception as e:
            logger.warning(f"Exception getting user info for {user_id}: {e}")
            return None
    
    def set_user_info(self, user_id: str, user_data: Dict[str, Any]) -> None:
        """手动设置用户信息缓存（用于外部已获取的数据）
        
        当外部代码已经调用了 get_user_info API，可以用此方法将结果存入缓存，
        避免后续重复请求。
        
        Args:
            user_id: 用户 ID
            user_data: API 返回的 data 字段
        """
        if not user_id or not user_data:
            return
        
        basic_info = user_data.get('basic_info', {})
        
        # 解析互动数据
        fans = follows = interaction = None
        for item in user_data.get('interactions', []):
            item_type = item.get('type')
            if item_type == 'fans':
                fans = item.get('count')
            elif item_type == 'follows':
                follows = item.get('count')
            elif item_type == 'interaction':
                interaction = item.get('count')
        
        user_info = UserInfoCache(
            user_id=user_id,
            nickname=basic_info.get('nickname'),
            avatar=basic_info.get('images'),
            desc=basic_info.get('desc'),
            fans=fans,
            follows=follows,
            interaction=interaction,
            fetch_time=time.time(),
            raw_data=user_data
        )
        
        with self._lock:
            self._user_info_cache[user_id] = user_info
        
        logger.debug(f"Manually cached user info for {user_id}")
    
    def get_cached_user_info(self, user_id: str) -> Optional[UserInfoCache]:
        """获取缓存的用户信息（不触发 API 请求）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            缓存的 UserInfoCache，不存在或已过期返回 None
        """
        with self._lock:
            cached = self._user_info_cache.get(user_id)
            if cached and self._is_user_info_valid(cached):
                return cached
        return None
    
    def invalidate_user_info(self, user_id: str) -> None:
        """使指定用户的信息缓存失效
        
        Args:
            user_id: 用户 ID
        """
        with self._lock:
            if user_id in self._user_info_cache:
                del self._user_info_cache[user_id]
    
    # ==================== URL 构建方法 ====================
    
    def build_user_url(self, user_id: str, token: Optional[str] = None) -> str:
        """构建用户主页 URL
        
        Args:
            user_id: 用户 ID
            token: 可选的 xsec_token，不提供则自动获取
            
        Returns:
            完整的用户主页 URL
        """
        base_url = self.USER_URL_TEMPLATE.format(user_id=user_id)
        
        # 如果没有提供 token，尝试获取
        if token is None:
            token = self.get_user_token(user_id)
        
        if token:
            return f"{base_url}?xsec_token={token}&xsec_source=pc_search"
        
        return base_url
    
    def build_note_url(self, note_id: str, token: Optional[str] = None) -> str:
        """构建笔记 URL
        
        Args:
            note_id: 笔记 ID
            token: 笔记的 xsec_token（通常从列表 API 获取）
            
        Returns:
            完整的笔记 URL
        """
        base_url = self.NOTE_URL_TEMPLATE.format(note_id=note_id)
        
        if token:
            return f"{base_url}?xsec_token={token}&xsec_source=pc_search"
        
        return base_url
    
    def build_note_url_with_fallback(
        self, 
        note_id: str, 
        note_token: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Tuple[str, str]:
        """构建笔记 URL，支持用户级 token 作为回退
        
        当笔记自身的 token 失效时，可以尝试使用用户级 token
        
        Args:
            note_id: 笔记 ID
            note_token: 笔记的 xsec_token
            user_id: 用户 ID（用于获取用户级 token 作为回退）
            
        Returns:
            (primary_url, fallback_url) 元组
        """
        primary_url = self.build_note_url(note_id, note_token)
        
        fallback_url = primary_url
        if user_id:
            user_token = self.get_user_token(user_id)
            if user_token and user_token != note_token:
                fallback_url = self.build_note_url(note_id, user_token)
        
        return primary_url, fallback_url
    
    def refresh_note_token(self, note_id: str, user_id: str) -> Optional[str]:
        """从用户笔记列表重新获取笔记的 xsec_token
        
        当笔记的 xsec_token 失效时，通过调用用户笔记列表 API 获取新的 token。
        
        Args:
            note_id: 笔记 ID
            user_id: 用户 ID
            
        Returns:
            新的 xsec_token，获取失败返回 None
        """
        if not note_id or not user_id or not self._xhs_apis:
            return None
        
        try:
            # 先获取用户级 token 用于调用笔记列表 API
            user_token = self.get_user_token(user_id, force_refresh=True)
            if not user_token:
                logger.warning(f"无法获取用户 {user_id} 的 token，无法刷新笔记 {note_id} 的 token")
                return None
            
            # 调用用户笔记列表 API
            success, msg, res_json = self._xhs_apis.get_user_note_info(
                user_id=user_id,
                cursor='',
                cookies_str=self._cookie_str,
                xsec_token=user_token,
                xsec_source='pc_search'
            )
            
            if not success or not res_json:
                logger.warning(f"获取用户笔记列表失败: {msg}")
                return None
            
            # 从笔记列表中查找目标笔记
            notes = res_json.get('data', {}).get('notes', [])
            for note in notes:
                nid = note.get('note_id') or note.get('id')
                if nid == note_id:
                    new_token = note.get('xsec_token')
                    if new_token:
                        logger.info(f"成功从用户笔记列表获取笔记 {note_id} 的新 xsec_token")
                        return new_token
            
            # 如果第一页没找到，可能需要翻页（但通常热门笔记在前面）
            logger.debug(f"笔记 {note_id} 未在用户 {user_id} 的第一页笔记列表中找到")
            
            # 尝试翻页查找（最多查找3页）
            cursor = res_json.get('data', {}).get('cursor', '')
            has_more = res_json.get('data', {}).get('has_more', False)
            
            for page in range(2, 4):  # 第2-3页
                if not has_more or not cursor:
                    break
                
                success, msg, res_json = self._xhs_apis.get_user_note_info(
                    user_id=user_id,
                    cursor=cursor,
                    cookies_str=self._cookie_str,
                    xsec_token=user_token,
                    xsec_source='pc_search'
                )
                
                if not success or not res_json:
                    break
                
                notes = res_json.get('data', {}).get('notes', [])
                for note in notes:
                    nid = note.get('note_id') or note.get('id')
                    if nid == note_id:
                        new_token = note.get('xsec_token')
                        if new_token:
                            logger.info(f"成功从用户笔记列表第{page}页获取笔记 {note_id} 的新 xsec_token")
                            return new_token
                
                cursor = res_json.get('data', {}).get('cursor', '')
                has_more = res_json.get('data', {}).get('has_more', False)
            
            logger.warning(f"在用户 {user_id} 的笔记列表中未找到笔记 {note_id}")
            
        except Exception as e:
            logger.warning(f"刷新笔记 {note_id} 的 token 时发生异常: {e}")
        
        return None
    
    @staticmethod
    def is_token_error(msg: str) -> bool:
        """检查错误消息是否与 xsec_token 相关
        
        Args:
            msg: 错误消息
            
        Returns:
            True 如果是 token 相关错误
        """
        if not msg:
            return False
        
        keywords = ['xsec', '签名', 'token', '参数错误', 'invalid signature']
        msg_lower = str(msg).lower()
        return any(keyword in msg_lower for keyword in keywords)
    
    def get_stats(self) -> Dict:
        """获取 token 管理器统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock:
            valid_token_count = sum(
                1 for info in self._token_cache.values() 
                if self._is_token_valid(info)
            )
            valid_user_info_count = sum(
                1 for info in self._user_info_cache.values()
                if self._is_user_info_valid(info)
            )
            return {
                'total_cached_tokens': len(self._token_cache),
                'valid_tokens': valid_token_count,
                'expired_tokens': len(self._token_cache) - valid_token_count,
                'total_cached_user_info': len(self._user_info_cache),
                'valid_user_info': valid_user_info_count,
                'expired_user_info': len(self._user_info_cache) - valid_user_info_count,
            }


# 全局实例（可选，用于需要共享状态的场景）
_global_token_manager: Optional[XsecTokenManager] = None
_global_lock = threading.Lock()


def get_token_manager(xhs_apis=None, cookie_str: str = None) -> Optional[XsecTokenManager]:
    """获取全局 Token 管理器实例
    
    Args:
        xhs_apis: XHS_Apis 实例（首次调用时必须提供）
        cookie_str: Cookie 字符串（首次调用时必须提供）
        
    Returns:
        XsecTokenManager 实例
    """
    global _global_token_manager
    
    with _global_lock:
        if _global_token_manager is None and xhs_apis and cookie_str:
            _global_token_manager = XsecTokenManager(xhs_apis, cookie_str)
        return _global_token_manager


def reset_token_manager() -> None:
    """重置全局 Token 管理器（用于测试或重新初始化）"""
    global _global_token_manager
    
    with _global_lock:
        if _global_token_manager:
            _global_token_manager.clear_cache()
        _global_token_manager = None


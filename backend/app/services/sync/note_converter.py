"""
Note Data Converter - 统一的笔记数据格式转换器

职责：
1. 解析计数值（支持 '10.1万'、'1.2亿' 等格式）
2. 从列表 API 数据转换为统一格式
3. 从详情 API 数据转换为统一格式
4. 智能合并新旧数据（保留已有字段）

使用场景：
- SyncService 中的 _convert_list_note() 和 _save_note()
- 其他需要处理笔记数据的模块
"""
import json
import time
from typing import Dict, Any, Optional, List, Union


class NoteDataConverter:
    """统一的笔记数据格式转换器
    
    提供静态方法，无需实例化即可使用。
    所有方法都是幂等的，不会修改输入数据。
    """
    
    # 标准化的笔记数据字段
    STANDARD_FIELDS = [
        'note_id', 'note_url', 'note_type', 'user_id', 'nickname', 'avatar',
        'title', 'desc', 'liked_count', 'collected_count', 'comment_count',
        'share_count', 'video_cover', 'video_addr', 'image_list', 'tags',
        'upload_time', 'ip_location', 'cover_remote', 'xsec_token',
    ]
    
    # 列表 API 不返回的字段（需要从详情 API 获取）
    LIST_API_MISSING_FIELDS = ['upload_time', 'desc', 'image_list', 'collected_count', 
                               'comment_count', 'share_count']
    
    @staticmethod
    def parse_count(value: Any) -> int:
        """解析计数值，支持中文单位格式
        
        支持的格式：
        - 整数: 100
        - 浮点数: 100.5
        - 字符串数字: "100"
        - 中文万: "10.1万" -> 101000
        - 中文亿: "1.2亿" -> 120000000
        
        Args:
            value: 计数值，可以是 int, float, str 或 None
            
        Returns:
            解析后的整数值，解析失败返回 0
            
        Examples:
            >>> NoteDataConverter.parse_count("10.1万")
            101000
            >>> NoteDataConverter.parse_count("1.2亿")
            120000000
            >>> NoteDataConverter.parse_count(None)
            0
        """
        if value is None:
            return 0
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return 0
            try:
                # 尝试直接转换
                return int(value)
            except ValueError:
                pass
            try:
                # 处理中文单位：万 (10000), 亿 (100000000)
                if '亿' in value:
                    num = float(value.replace('亿', ''))
                    return int(num * 100000000)
                elif '万' in value:
                    num = float(value.replace('万', ''))
                    return int(num * 10000)
                else:
                    return int(float(value))
            except (ValueError, TypeError):
                return 0
        return 0
    
    @staticmethod
    def parse_count_nullable(value: Any) -> Optional[int]:
        """解析计数值，保留 None 语义
        
        与 parse_count 类似，但当输入为 None 时返回 None 而不是 0。
        用于区分"没有数据"和"数据为 0"的场景。
        
        Args:
            value: 计数值
            
        Returns:
            解析后的整数值，输入为 None 时返回 None
        """
        if value is None:
            return None
        return NoteDataConverter.parse_count(value)
    
    @staticmethod
    def _extract_cover_url(cover_info: Any) -> str:
        """从封面信息中提取 URL
        
        处理多种封面数据格式：
        - 字符串 URL
        - 包含 info_list 的字典
        - 包含 url/url_default 的字典
        
        Args:
            cover_info: 封面信息，可能是字符串或字典
            
        Returns:
            封面 URL 字符串
        """
        if not cover_info:
            return ''
        
        if isinstance(cover_info, str):
            return cover_info
        
        if isinstance(cover_info, dict):
            # 尝试从 info_list 获取高质量图片
            info_list = cover_info.get('info_list') or cover_info.get('url_default') or []
            if isinstance(info_list, list) and len(info_list) > 0:
                last_item = info_list[-1]
                if isinstance(last_item, dict):
                    return last_item.get('url', '')
                elif isinstance(last_item, str):
                    return last_item
            elif isinstance(info_list, str):
                return info_list
            
            # 回退到 url 字段
            return cover_info.get('url') or cover_info.get('url_default') or ''
        
        return ''
    
    @staticmethod
    def _normalize_note_type(note_type: str) -> str:
        """标准化笔记类型
        
        Args:
            note_type: 原始笔记类型
            
        Returns:
            标准化后的类型：'图集' 或 '视频'
        """
        if note_type == 'video':
            return '视频'
        elif note_type == 'normal' or not note_type:
            return '图集'
        return note_type
    
    @staticmethod
    def _timestamp_to_str(timestamp: int) -> str:
        """将毫秒时间戳转换为字符串格式
        
        Args:
            timestamp: 毫秒时间戳
            
        Returns:
            格式化的时间字符串 "YYYY-MM-DD HH:MM:SS"
        """
        time_local = time.localtime(timestamp / 1000)
        return time.strftime("%Y-%m-%d %H:%M:%S", time_local)
    
    @staticmethod
    def convert_from_list_api(
        simple_note: Dict[str, Any],
        user_id: str = None,
        existing_note: Any = None
    ) -> Dict[str, Any]:
        """从列表 API 数据转换为统一格式
        
        列表 API (get_user_all_notes) 返回的数据结构与详情 API 不同，
        且缺少部分字段（upload_time、完整 desc、完整 image_list 等）。
        
        重要：列表 API 不返回以下字段：
        - upload_time (发布时间) - 只能从详情 API 获取
        - desc (完整内容详情) - 列表 API 可能为空或截断
        - image_list (完整图片列表) - 列表 API 只有封面图
        - collected_count, comment_count, share_count - 部分响应可能缺失
        
        Args:
            simple_note: 列表 API 返回的笔记数据
            user_id: 用户 ID（如果笔记数据中没有）
            existing_note: 已存在的 Note 对象，用于保留已有字段
            
        Returns:
            统一格式的笔记数据字典
        """
        note_id = simple_note.get('note_id') or simple_note.get('id') or ''
        
        # 提取用户信息（支持嵌套和扁平两种结构）
        user_info = simple_note.get('user') or {}
        note_user_id = user_info.get('user_id') or simple_note.get('user_id') or user_id or ''
        nickname = user_info.get('nickname') or simple_note.get('nickname') or ''
        avatar = user_info.get('avatar') or simple_note.get('avatar') or ''
        
        # 标题处理
        title = simple_note.get('display_title') or simple_note.get('title') or ''
        if not title or title.strip() == '':
            title = '无标题'
        
        # 笔记类型标准化
        note_type = NoteDataConverter._normalize_note_type(
            simple_note.get('type') or 'normal'
        )
        
        # 互动数据处理 - 可能是嵌套结构或扁平结构
        interact_info = simple_note.get('interact_info') or {}
        
        # liked_count 通常在列表 API 中可用
        liked_count = NoteDataConverter.parse_count(
            interact_info.get('liked_count') or simple_note.get('liked_count')
        )
        
        # 这些计数可能在列表 API 中缺失，保留 None 语义以便后续合并
        collected_count = NoteDataConverter.parse_count_nullable(
            interact_info.get('collected_count') or simple_note.get('collected_count')
        )
        comment_count = NoteDataConverter.parse_count_nullable(
            interact_info.get('comment_count') or simple_note.get('comment_count')
        )
        share_count = NoteDataConverter.parse_count_nullable(
            interact_info.get('share_count') or simple_note.get('share_count')
        )
        
        # 从已存在的笔记中保留缺失字段
        if existing_note:
            if collected_count is None and getattr(existing_note, 'collected_count', None) is not None:
                collected_count = existing_note.collected_count
            if comment_count is None and getattr(existing_note, 'comment_count', None) is not None:
                comment_count = existing_note.comment_count
            if share_count is None and getattr(existing_note, 'share_count', None) is not None:
                share_count = existing_note.share_count
        
        # 封面图处理
        cover_url = NoteDataConverter._extract_cover_url(simple_note.get('cover'))
        
        # 构建笔记 URL
        xsec_token = simple_note.get('xsec_token') or ''
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        if xsec_token:
            note_url = f"{note_url}?xsec_token={xsec_token}&xsec_source=pc_search"
        
        # 关键字段：upload_time - 列表 API 不返回此字段
        upload_time = simple_note.get('upload_time')
        if not upload_time and existing_note:
            upload_time = getattr(existing_note, 'upload_time', None)
        
        # desc - 列表 API 可能为空或截断
        desc = simple_note.get('desc') or ''
        if not desc and existing_note and getattr(existing_note, 'desc', None):
            desc = existing_note.desc
        
        # image_list - 列表 API 只有封面，保留已存在的完整列表
        image_list = [cover_url] if cover_url else []
        if existing_note and getattr(existing_note, 'image_list', None):
            try:
                existing_images = existing_note.image_list
                if isinstance(existing_images, str):
                    existing_images = json.loads(existing_images)
                if isinstance(existing_images, list) and len(existing_images) > len(image_list):
                    image_list = existing_images
            except Exception:
                pass
        
        # video_addr - 列表 API 可能没有
        video_addr = simple_note.get('video_addr')
        if not video_addr and existing_note:
            video_addr = getattr(existing_note, 'video_addr', None)
        
        # ip_location
        ip_location = simple_note.get('ip_location')
        if not ip_location and existing_note:
            ip_location = getattr(existing_note, 'ip_location', '')
        
        return {
            'note_id': note_id,
            'note_url': note_url,
            'note_type': note_type,
            'user_id': note_user_id,
            'nickname': nickname,
            'avatar': avatar,
            'title': title,
            'desc': desc,
            'liked_count': liked_count,
            'collected_count': collected_count,
            'comment_count': comment_count,
            'share_count': share_count,
            'video_cover': cover_url if note_type == '视频' else None,
            'video_addr': video_addr,
            'image_list': image_list,
            'tags': simple_note.get('tags') or [],
            'upload_time': upload_time,
            'ip_location': ip_location or '',
            'cover_remote': cover_url,
            'xsec_token': xsec_token,
            # 标记数据来源（用于调试和后续处理）
            '_from_list_api': True,
        }
    
    @staticmethod
    def convert_from_detail_api(data: Dict[str, Any]) -> Dict[str, Any]:
        """从详情 API 数据转换为统一格式
        
        详情 API 返回完整的笔记数据，包括 upload_time、完整 desc、
        完整 image_list 等列表 API 不提供的字段。
        
        此方法兼容 Spider_XHS 的 handle_note_info 函数格式。
        
        Args:
            data: 详情 API 返回的原始数据（包含 note_card 结构）
            
        Returns:
            统一格式的笔记数据字典
        """
        note_id = data.get('id', '')
        note_url = data.get('url', '')
        
        note_card = data.get('note_card', {})
        
        # 笔记类型
        note_type = NoteDataConverter._normalize_note_type(note_card.get('type', 'normal'))
        
        # 用户信息
        user_info = note_card.get('user', {})
        user_id = user_info.get('user_id', '')
        nickname = user_info.get('nickname', '')
        avatar = user_info.get('avatar', '')
        
        # 标题和描述
        title = note_card.get('title', '')
        if not title or title.strip() == '':
            title = '无标题'
        desc = note_card.get('desc', '')
        
        # 互动数据
        interact_info = note_card.get('interact_info', {})
        liked_count = NoteDataConverter.parse_count(interact_info.get('liked_count'))
        collected_count = NoteDataConverter.parse_count(interact_info.get('collected_count'))
        comment_count = NoteDataConverter.parse_count(interact_info.get('comment_count'))
        share_count = NoteDataConverter.parse_count(interact_info.get('share_count'))
        
        # 图片列表
        image_list_temp = note_card.get('image_list', [])
        image_list = []
        for image in image_list_temp:
            try:
                info_list = image.get('info_list', [])
                if len(info_list) > 1:
                    image_list.append(info_list[1].get('url', ''))
                elif len(info_list) > 0:
                    image_list.append(info_list[0].get('url', ''))
            except Exception:
                pass
        
        # 视频信息
        video_cover = None
        video_addr = None
        if note_type == '视频':
            video_cover = image_list[0] if image_list else None
            video_info = note_card.get('video', {}).get('consumer', {})
            origin_key = video_info.get('origin_video_key', '')
            if origin_key:
                video_addr = f'https://sns-video-bd.xhscdn.com/{origin_key}'
        
        # 标签
        tags_temp = note_card.get('tag_list', [])
        tags = []
        for tag in tags_temp:
            try:
                tag_name = tag.get('name', '')
                if tag_name:
                    tags.append(tag_name)
            except Exception:
                pass
        
        # 上传时间（毫秒时间戳转字符串）
        timestamp = note_card.get('time')
        upload_time = NoteDataConverter._timestamp_to_str(timestamp) if timestamp else ''
        
        # IP 归属地
        ip_location = note_card.get('ip_location', '未知')
        
        # 封面
        cover_remote = image_list[0] if image_list else ''
        
        return {
            'note_id': note_id,
            'note_url': note_url,
            'note_type': note_type,
            'user_id': user_id,
            'nickname': nickname,
            'avatar': avatar,
            'title': title,
            'desc': desc,
            'liked_count': liked_count,
            'collected_count': collected_count,
            'comment_count': comment_count,
            'share_count': share_count,
            'video_cover': video_cover,
            'video_addr': video_addr,
            'image_list': image_list,
            'tags': tags,
            'upload_time': upload_time,
            'ip_location': ip_location,
            'cover_remote': cover_remote,
            'xsec_token': '',
            '_from_detail_api': True,
        }
    
    @staticmethod
    def merge_note_data(
        existing: Dict[str, Any],
        new_data: Dict[str, Any],
        prefer_new: List[str] = None
    ) -> Dict[str, Any]:
        """智能合并新旧笔记数据
        
        合并策略：
        1. 新数据中的非空值优先（除非在 prefer_existing 列表中）
        2. 保留已有的 upload_time、desc、image_list 等详情字段
        3. 互动数据（点赞、收藏等）始终使用新值（如果有）
        
        Args:
            existing: 已存在的笔记数据字典
            new_data: 新获取的笔记数据字典
            prefer_new: 即使已有值也使用新值的字段列表
            
        Returns:
            合并后的笔记数据字典
        """
        if not existing:
            return new_data.copy() if new_data else {}
        if not new_data:
            return existing.copy()
        
        prefer_new = prefer_new or []
        
        # 始终使用新值的字段（互动数据）
        always_update_fields = ['liked_count', 'collected_count', 'comment_count', 
                                'share_count', 'last_updated']
        
        # 仅在已有值为空时使用新值的字段（详情数据）
        preserve_if_exists_fields = ['upload_time', 'desc', 'image_list', 'video_addr']
        
        merged = existing.copy()
        
        for key, new_value in new_data.items():
            # 跳过内部标记字段
            if key.startswith('_'):
                continue
            
            old_value = merged.get(key)
            
            # 始终更新的字段
            if key in always_update_fields:
                if new_value is not None:
                    merged[key] = new_value
                continue
            
            # 强制使用新值的字段
            if key in prefer_new:
                if new_value is not None:
                    merged[key] = new_value
                continue
            
            # 保留已有值的字段
            if key in preserve_if_exists_fields:
                if NoteDataConverter._is_empty(old_value) and not NoteDataConverter._is_empty(new_value):
                    merged[key] = new_value
                continue
            
            # 默认：新值非空时使用新值
            if not NoteDataConverter._is_empty(new_value):
                merged[key] = new_value
        
        # 特殊处理 image_list：保留更长的列表
        if 'image_list' in new_data and 'image_list' in existing:
            new_images = new_data.get('image_list') or []
            old_images = existing.get('image_list') or []
            if isinstance(old_images, str):
                try:
                    old_images = json.loads(old_images)
                except Exception:
                    old_images = []
            if isinstance(new_images, str):
                try:
                    new_images = json.loads(new_images)
                except Exception:
                    new_images = []
            # 保留更完整的图片列表
            if len(new_images) > len(old_images):
                merged['image_list'] = new_images
            else:
                merged['image_list'] = old_images
        
        return merged
    
    @staticmethod
    def _is_empty(value: Any) -> bool:
        """检查值是否为空
        
        空值定义：
        - None
        - 空字符串或只有空白的字符串
        - 空列表
        - 空字典
        - 0（数字 0 不算空）
        
        Args:
            value: 要检查的值
            
        Returns:
            True 如果值为空
        """
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() == ''
        if isinstance(value, (list, dict)):
            return len(value) == 0
        return False
    
    @staticmethod
    def is_data_complete(note_data: Dict[str, Any]) -> bool:
        """检查笔记数据是否完整
        
        完整的数据应该来自详情 API，包含：
        - upload_time（发布时间）
        - desc（描述，可以是空字符串但不能是 None）
        
        Args:
            note_data: 笔记数据字典
            
        Returns:
            True 如果数据完整
        """
        if not note_data:
            return False
        
        # upload_time 是关键指标 - 列表 API 不返回此字段
        upload_time = note_data.get('upload_time')
        if upload_time is None or (isinstance(upload_time, str) and upload_time.strip() == ''):
            return False
        
        # desc 不应为 None（空字符串是允许的）
        if note_data.get('desc') is None:
            return False
        
        return True
    
    @staticmethod
    def get_missing_fields(note_data: Dict[str, Any]) -> List[str]:
        """获取笔记数据中缺失的字段列表
        
        用于调试和日志记录，帮助识别需要从详情 API 补充的字段。
        
        Args:
            note_data: 笔记数据字典
            
        Returns:
            缺失字段名列表
        """
        missing = []
        
        if not note_data:
            return NoteDataConverter.STANDARD_FIELDS.copy()
        
        # 检查关键字段
        upload_time = note_data.get('upload_time')
        if upload_time is None or (isinstance(upload_time, str) and upload_time.strip() == ''):
            missing.append('upload_time')
        
        if note_data.get('desc') is None:
            missing.append('desc')
        
        # 检查图片列表
        image_list = note_data.get('image_list')
        if not image_list or (isinstance(image_list, list) and len(image_list) <= 1):
            missing.append('image_list')
        
        # 检查计数字段
        if note_data.get('collected_count') is None:
            missing.append('collected_count')
        if note_data.get('comment_count') is None:
            missing.append('comment_count')
        if note_data.get('share_count') is None:
            missing.append('share_count')
        
        return missing


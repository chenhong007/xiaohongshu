"""
笔记持久化服务 - 统一管理笔记数据的数据库存储

将 _save_note() 和 _bulk_save_notes() 中的重复字段更新逻辑抽取到此模块，
提供统一的笔记保存、批量保存和字段更新接口。
"""
import json
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Callable

from ...extensions import db
from ...models import Note
from ...utils.logger import get_logger

logger = get_logger('persistence')


class NotePersistenceService:
    """笔记数据库持久化服务
    
    提供统一的笔记保存接口，消除 SyncService 中的重复代码。
    
    主要功能：
    - save_single: 保存单条笔记（新增或更新）
    - bulk_save: 批量保存笔记（高性能批量插入）
    - update_fields: 智能更新笔记字段
    """
    
    # 基础字段：总是更新
    BASIC_FIELDS = ['nickname', 'avatar', 'title', 'type']
    
    # 条件更新字段：仅当新值非空时更新
    CONDITIONAL_FIELDS = [
        'desc', 'upload_time', 'video_addr', 'ip_location', 
        'cover_remote', 'xsec_token'
    ]
    
    # 计数字段：仅当新值非 None 时更新
    COUNT_FIELDS = ['liked_count', 'collected_count', 'comment_count', 'share_count']
    
    # JSON 列表字段：需要特殊处理
    JSON_FIELDS = ['image_list', 'tags']
    
    @staticmethod
    def parse_count(value) -> int:
        """解析计数值，支持中文单位（如 '10.1万'、'1.2亿'）
        
        Args:
            value: 计数值，可以是 int、str（如 '10.1万'）或 None
            
        Returns:
            整数计数值
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
                return int(value)
            except ValueError:
                pass
            try:
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
    def calculate_cover_url(note_data: Dict) -> Optional[str]:
        """计算笔记封面 URL
        
        优先级：cover_remote > video_cover > image_list[0]
        
        Args:
            note_data: 笔记数据字典
            
        Returns:
            封面 URL 或 None
        """
        cover_remote = note_data.get('cover_remote') or note_data.get('video_cover')
        if not cover_remote:
            imgs = note_data.get('image_list') or []
            cover_remote = imgs[0] if imgs else None
        return cover_remote
    
    @staticmethod
    def update_fields(note: Note, data: Dict, fields: List[str] = None) -> bool:
        """智能更新笔记字段
        
        根据字段类型应用不同的更新策略：
        - 基础字段：直接覆盖
        - 条件字段：仅当新值非空时更新
        - 计数字段：仅当新值非 None 时更新（支持中文单位解析）
        - JSON 字段：智能合并（image_list 保留更多图片）
        
        Args:
            note: Note 模型实例
            data: 新数据字典
            fields: 可选，指定要更新的字段列表；为 None 时更新所有字段
            
        Returns:
            是否有字段被更新
        """
        updated = False
        
        # 基础字段：直接覆盖
        basic_fields = fields or NotePersistenceService.BASIC_FIELDS
        for field in basic_fields:
            if field in NotePersistenceService.BASIC_FIELDS:
                # note_type -> type 的字段映射
                data_key = 'note_type' if field == 'type' else field
                if data_key in data:
                    setattr(note, field, data[data_key])
                    updated = True
        
        # 条件字段：仅当新值非空时更新
        conditional_fields = fields or NotePersistenceService.CONDITIONAL_FIELDS
        for field in conditional_fields:
            if field in NotePersistenceService.CONDITIONAL_FIELDS:
                value = data.get(field)
                if value:
                    setattr(note, field, value)
                    updated = True
        
        # 计数字段：仅当新值非 None 时更新
        count_fields = fields or NotePersistenceService.COUNT_FIELDS
        for field in count_fields:
            if field in NotePersistenceService.COUNT_FIELDS:
                value = data.get(field)
                if value is not None:
                    parsed = NotePersistenceService.parse_count(value)
                    setattr(note, field, parsed)
                    updated = True
        
        # JSON 字段：特殊处理
        if fields is None or 'image_list' in fields:
            if data.get('image_list'):
                new_count = len(data['image_list'])
                old_list = json.loads(note.image_list) if note.image_list else []
                # 保留更多图片的版本
                if new_count > len(old_list) or len(old_list) <= 1:
                    note.image_list = json.dumps(data['image_list'])
                    updated = True
        
        if fields is None or 'tags' in fields:
            if data.get('tags'):
                note.tags = json.dumps(data['tags'])
                updated = True
        
        # 更新时间戳
        if updated:
            note.last_updated = datetime.utcnow()
        
        return updated
    
    @staticmethod
    def save_single(
        note_data: Dict,
        download_media: bool = False,
        auto_commit: bool = True,
        cover_callback: Callable[[str, str], None] = None,
        media_callback: Callable[[str, Dict], None] = None
    ) -> Optional[Note]:
        """保存单条笔记
        
        如果笔记已存在则更新，否则新增。
        
        Args:
            note_data: 笔记数据字典，需包含 note_id
            download_media: 是否下载媒体文件
            auto_commit: 是否自动提交事务
            cover_callback: 封面下载回调 (cover_url, note_id)
            media_callback: 媒体下载回调 (note_id, note_data)
            
        Returns:
            保存的 Note 实例，失败返回 None
            
        Raises:
            Exception: 数据库操作失败时抛出
        """
        try:
            note_id = note_data.get('note_id')
            if not note_id:
                logger.debug("跳过保存：note_id 为空")
                return None
            
            # 计算封面 URL
            cover_remote = NotePersistenceService.calculate_cover_url(note_data)
            if cover_remote:
                note_data['cover_remote'] = cover_remote
            
            note = Note.query.filter_by(note_id=note_id).first()
            
            if note:
                # 更新已存在的笔记
                NotePersistenceService.update_fields(note, note_data)
                # 单独处理 desc（条件更新）
                if note_data.get('desc'):
                    note.desc = note_data['desc']
            else:
                # 创建新笔记
                note = NotePersistenceService._create_note(note_data, cover_remote)
                db.session.add(note)
            
            if auto_commit:
                db.session.commit()
            
            # 异步媒体下载回调
            if cover_callback and cover_remote:
                cover_callback(cover_remote, note_id)
            if media_callback and download_media:
                media_callback(note_id, note_data)
            
            return note
            
        except Exception as e:
            db.session.rollback()
            logger.warning(f"保存笔记 {note_data.get('note_id')} 失败: {e}")
            raise
    
    @staticmethod
    def bulk_save(
        notes_data: List[Dict],
        existing_cache: Dict[str, Note] = None,
        cover_callback: Callable[[str, str], None] = None
    ) -> Tuple[int, int]:
        """批量保存笔记
        
        高性能批量保存，使用 bulk_insert_mappings 进行批量插入。
        
        Args:
            notes_data: 笔记数据列表
            existing_cache: 可选，已存在笔记的缓存 {note_id: Note}
            cover_callback: 封面下载回调 (cover_url, note_id)
            
        Returns:
            (插入数量, 更新数量) 元组
            
        Raises:
            Exception: 数据库操作失败时抛出
        """
        if not notes_data:
            return 0, 0
        
        try:
            # 预取已存在的笔记（如果未提供缓存）
            if existing_cache is None:
                note_ids = [n.get('note_id') for n in notes_data if n.get('note_id')]
                existing_notes = Note.query.filter(Note.note_id.in_(note_ids)).all()
                existing_cache = {n.note_id: n for n in existing_notes}
            
            existing_ids = set(existing_cache.keys())
            insert_mappings = []
            update_count = 0
            now = datetime.utcnow()
            cover_tasks = []
            
            for note_data in notes_data:
                note_id = note_data.get('note_id')
                if not note_id:
                    continue
                
                # 计算封面 URL
                cover_remote = NotePersistenceService.calculate_cover_url(note_data)
                if cover_remote:
                    cover_tasks.append((cover_remote, note_id))
                
                if note_id in existing_ids:
                    # 更新已存在的笔记
                    note = existing_cache.get(note_id)
                    if note:
                        NotePersistenceService.update_fields(note, note_data)
                        # 单独处理 desc
                        if note_data.get('desc'):
                            note.desc = note_data['desc']
                        # 单独处理 cover_remote
                        if cover_remote:
                            note.cover_remote = cover_remote
                        note.last_updated = now
                        update_count += 1
                else:
                    # 构建插入映射
                    mapping = NotePersistenceService._build_insert_mapping(
                        note_data, cover_remote, now
                    )
                    insert_mappings.append(mapping)
            
            # 批量插入
            if insert_mappings:
                db.session.bulk_insert_mappings(Note, insert_mappings)
            
            db.session.commit()
            
            # 触发封面下载回调
            if cover_callback and cover_tasks:
                for cover_url, nid in cover_tasks:
                    cover_callback(cover_url, nid)
            
            return len(insert_mappings), update_count
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"[批量保存] 失败: {e}")
            raise
    
    @staticmethod
    def _create_note(note_data: Dict, cover_remote: Optional[str] = None) -> Note:
        """创建新的 Note 实例
        
        Args:
            note_data: 笔记数据字典
            cover_remote: 封面 URL
            
        Returns:
            Note 实例
        """
        return Note(
            note_id=note_data['note_id'],
            user_id=note_data['user_id'],
            nickname=note_data['nickname'],
            avatar=note_data['avatar'],
            title=note_data['title'],
            desc=note_data.get('desc') or '',
            type=note_data['note_type'],
            liked_count=NotePersistenceService.parse_count(note_data.get('liked_count')) or 0,
            collected_count=NotePersistenceService.parse_count(note_data.get('collected_count')) or 0,
            comment_count=NotePersistenceService.parse_count(note_data.get('comment_count')) or 0,
            share_count=NotePersistenceService.parse_count(note_data.get('share_count')) or 0,
            upload_time=note_data.get('upload_time') or '',
            video_addr=note_data.get('video_addr') or '',
            image_list=json.dumps(note_data['image_list']) if note_data.get('image_list') else '[]',
            tags=json.dumps(note_data['tags']) if note_data.get('tags') else '[]',
            ip_location=note_data.get('ip_location') or '',
            cover_remote=cover_remote or '',
            cover_local='',
            xsec_token=note_data.get('xsec_token') or '',
        )
    
    @staticmethod
    def _build_insert_mapping(
        note_data: Dict, 
        cover_remote: Optional[str], 
        timestamp: datetime
    ) -> Dict:
        """构建批量插入的映射字典
        
        Args:
            note_data: 笔记数据
            cover_remote: 封面 URL
            timestamp: 更新时间戳
            
        Returns:
            用于 bulk_insert_mappings 的字典
        """
        return {
            'note_id': note_data['note_id'],
            'user_id': note_data['user_id'],
            'nickname': note_data['nickname'],
            'avatar': note_data['avatar'],
            'title': note_data['title'],
            'desc': note_data.get('desc') or '',
            'type': note_data['note_type'],
            'liked_count': NotePersistenceService.parse_count(note_data.get('liked_count')) or 0,
            'collected_count': NotePersistenceService.parse_count(note_data.get('collected_count')) or 0,
            'comment_count': NotePersistenceService.parse_count(note_data.get('comment_count')) or 0,
            'share_count': NotePersistenceService.parse_count(note_data.get('share_count')) or 0,
            'upload_time': note_data.get('upload_time') or '',
            'video_addr': note_data.get('video_addr') or '',
            'image_list': json.dumps(note_data['image_list']) if note_data.get('image_list') else '[]',
            'tags': json.dumps(note_data['tags']) if note_data.get('tags') else '[]',
            'ip_location': note_data.get('ip_location') or '',
            'cover_remote': cover_remote or '',
            'cover_local': '',
            'xsec_token': note_data.get('xsec_token') or '',
            'last_updated': timestamp,
        }


"""
Note Validator - Validate note data completeness

This module provides note validation logic for ensuring data integrity:
- Notes within 7*24 hours: Always need full update (all fields)
- Notes older than 7*24 hours: Only update if critical fields are missing

The validator is used:
1. Before deep sync: Identify which notes need to be fetched
2. After deep sync: Verify all notes have complete data
"""
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple, TYPE_CHECKING

from ...utils.logger import get_logger

if TYPE_CHECKING:
    from ...models import Note

logger = get_logger('note_validator')


class NoteValidator:
    """Validator for checking note data completeness.
    
    Validation Rules:
    - Notes within 7*24 hours (168 hours): Always need full update
      (data may still be changing, need fresh data)
    - Notes older than 7*24 hours: Only update if critical fields are missing
      (upload_time, desc, etc.)
    
    This ensures:
    1. Recent notes always get the latest data
    2. Old notes with complete data are skipped (save API calls)
    3. Old notes with missing fields still get updated
    
    Field Categories (based on DownloadPage table columns):
    =====================================================
    
    1. CRITICAL_FIELDS - 关键字段（只能从详情API获取）:
       - upload_time: 发布时间 - 列表API永远不返回
       - desc: 内容详情 - 列表API可能返回空或截断
    
    2. BASIC_FIELDS - 基础字段（列表API通常返回）:
       - note_id: 笔记ID
       - user_id: 用户ID
       - type: 笔记类型（图集/视频）
       - title: 标题
       - nickname: 博主昵称
       - avatar: 博主头像
    
    3. INTERACTION_FIELDS - 互动数据字段:
       - liked_count: 点赞数 - 列表API通常返回
       - collected_count: 收藏数 - 详情API（列表可能缺失）
       - comment_count: 评论数 - 详情API（列表可能缺失）
       - share_count: 转发数 - 详情API（列表可能缺失）
    
    4. MEDIA_FIELDS - 媒体字段:
       - cover_remote: 远程封面URL
       - cover_local: 本地封面路径
       - image_list: 图片列表（详情API返回完整列表）
       - video_addr: 视频地址（视频类型笔记）
    """
    
    # Time threshold: 7 days (168 hours)
    RECENT_NOTE_THRESHOLD_HOURS = 7 * 24  # 168 hours
    
    # Critical fields that must be present (only from detail API)
    # These are THE key indicators for data completeness
    CRITICAL_FIELDS = ['upload_time', 'desc']
    
    # Basic fields that should always be present
    BASIC_FIELDS = ['note_id', 'user_id', 'type', 'title', 'nickname', 'avatar']
    
    # Interaction fields - may be missing from list API
    INTERACTION_FIELDS = ['liked_count', 'collected_count', 'comment_count', 'share_count']
    
    # Media fields
    MEDIA_FIELDS = ['cover_remote', 'cover_local', 'image_list', 'video_addr']
    
    # All table display fields (for DownloadPage)
    # These are all the fields shown in the notes table
    TABLE_DISPLAY_FIELDS = [
        'type',           # 类型
        'cover_local',    # 预览（本地封面）
        'cover_remote',   # 远程URL
        'upload_time',    # 发布时间
        'nickname',       # 博主
        'avatar',         # 博主头像
        'title',          # 标题
        'desc',           # 内容详情
        'liked_count',    # 点赞
        'collected_count',# 收藏
        'comment_count',  # 评论
        'share_count',    # 转发
    ]
    
    # Legacy alias for backward compatibility
    SECONDARY_FIELDS = ['collected_count', 'comment_count', 'share_count']
    
    @staticmethod
    def is_recent_note(note: 'Note') -> bool:
        """Check if note was uploaded within the recent threshold.
        
        Args:
            note: Note object to check
            
        Returns:
            True if note is within 7*24 hours, False otherwise
            Returns True if upload_time is missing (treat as recent to force update)
        """
        upload_time = getattr(note, 'upload_time', None)
        
        # If no upload_time, treat as recent (needs update)
        if not upload_time or (isinstance(upload_time, str) and upload_time.strip() == ''):
            return True
        
        try:
            # Parse upload_time
            upload_dt = None
            if isinstance(upload_time, (int, float)):
                upload_dt = datetime.fromtimestamp(upload_time)
            elif isinstance(upload_time, str):
                # Try various formats
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d']:
                    try:
                        upload_dt = datetime.strptime(upload_time, fmt)
                        break
                    except ValueError:
                        continue
            
            if upload_dt:
                age_hours = (datetime.utcnow() - upload_dt).total_seconds() / 3600
                return age_hours <= NoteValidator.RECENT_NOTE_THRESHOLD_HOURS
            
            # If parsing failed, treat as recent (needs update)
            return True
            
        except Exception as e:
            logger.debug(f"Error parsing upload_time for note: {e}")
            return True
    
    @staticmethod
    def get_missing_critical_fields(note: 'Note') -> List[str]:
        """Get list of missing critical fields.
        
        Critical fields are those that can ONLY be obtained from detail API:
        - upload_time: Publication time
        - desc: Full description
        
        Args:
            note: Note object to check
            
        Returns:
            List of missing critical field names
        """
        if not note:
            return NoteValidator.CRITICAL_FIELDS.copy()
        
        missing = []
        
        def is_blank(value):
            return value is None or (isinstance(value, str) and value.strip() == '')
        
        # upload_time is THE key indicator - list API never returns it
        if is_blank(getattr(note, 'upload_time', None)):
            missing.append('upload_time')
        
        # desc should not be None (empty string is OK - user may not have written description)
        if getattr(note, 'desc', None) is None:
            missing.append('desc')
        
        return missing
    
    @staticmethod
    def get_missing_secondary_fields(note: 'Note') -> List[str]:
        """Get list of missing secondary fields.
        
        Secondary fields may be missing from list API responses.
        
        Args:
            note: Note object to check
            
        Returns:
            List of missing secondary field names
        """
        if not note:
            return NoteValidator.SECONDARY_FIELDS.copy()
        
        missing = []
        
        for field in NoteValidator.SECONDARY_FIELDS:
            if getattr(note, field, None) is None:
                missing.append(field)
        
        return missing
    
    @staticmethod
    def get_missing_basic_fields(note: 'Note') -> List[str]:
        """Get list of missing basic fields.
        
        Basic fields are those that should always be present from list API.
        
        Args:
            note: Note object to check
            
        Returns:
            List of missing basic field names
        """
        if not note:
            return NoteValidator.BASIC_FIELDS.copy()
        
        missing = []
        
        def is_blank(value):
            return value is None or (isinstance(value, str) and value.strip() == '')
        
        for field in NoteValidator.BASIC_FIELDS:
            if is_blank(getattr(note, field, None)):
                missing.append(field)
        
        return missing
    
    @staticmethod
    def get_missing_interaction_fields(note: 'Note') -> List[str]:
        """Get list of missing interaction fields.
        
        Interaction fields may be missing from list API responses.
        
        Args:
            note: Note object to check
            
        Returns:
            List of missing interaction field names
        """
        if not note:
            return NoteValidator.INTERACTION_FIELDS.copy()
        
        missing = []
        
        for field in NoteValidator.INTERACTION_FIELDS:
            if getattr(note, field, None) is None:
                missing.append(field)
        
        return missing
    
    @staticmethod
    def get_missing_media_fields(note: 'Note') -> List[str]:
        """Get list of missing media fields.
        
        Args:
            note: Note object to check
            
        Returns:
            List of missing media field names
        """
        if not note:
            return ['cover_local', 'image_list']
        
        missing = []
        
        def is_blank(value):
            return value is None or (isinstance(value, str) and value.strip() == '')
        
        # Cover fields
        if is_blank(getattr(note, 'cover_local', None)):
            missing.append('cover_local')
        
        # Media based on note type
        note_type = getattr(note, 'type', '')
        if note_type == '视频':
            if is_blank(getattr(note, 'video_addr', None)):
                missing.append('video_addr')
        else:
            try:
                image_list = json.loads(note.image_list) if note.image_list else []
            except Exception:
                image_list = []
            # List API only returns cover, so image_list <= 1 means no detail fetched
            if len(image_list) <= 1:
                missing.append('image_list')
        
        return missing
    
    @staticmethod
    def needs_deep_sync(note: 'Note') -> Tuple[bool, List[str]]:
        """Check if note needs deep sync (detail API fetch).
        
        Decision logic:
        1. If note is recent (within 7*24 hours): Always needs update
        2. If note is old (> 7*24 hours): Only needs update if critical fields missing
        
        Args:
            note: Note object to check
            
        Returns:
            Tuple of (needs_sync: bool, reasons: List[str])
            - needs_sync: True if note needs to be fetched via detail API
            - reasons: List of reasons why sync is needed
        """
        if not note:
            return True, ['note_not_exists']
        
        reasons = []
        
        # Check if recent note
        is_recent = NoteValidator.is_recent_note(note)
        
        if is_recent:
            # Recent notes always need full update
            reasons.append('recent_note_within_7d')
            return True, reasons
        
        # For old notes, check critical fields
        missing_critical = NoteValidator.get_missing_critical_fields(note)
        if missing_critical:
            reasons.extend([f'missing_{f}' for f in missing_critical])
            return True, reasons
        
        # Old note with complete critical fields - no sync needed
        return False, []
    
    @staticmethod
    def is_data_complete(note: 'Note', check_media: bool = False) -> bool:
        """Check if note has complete data.
        
        Args:
            note: Note object to check
            check_media: Whether to also check media fields
            
        Returns:
            True if note data is complete
        """
        if not note:
            return False
        
        # Check critical fields
        missing_critical = NoteValidator.get_missing_critical_fields(note)
        if missing_critical:
            return False
        
        # Optionally check media
        if check_media:
            missing_media = NoteValidator.get_missing_media_fields(note)
            if missing_media:
                return False
        
        return True
    
    @staticmethod
    def validate_notes_batch(
        notes: List['Note'],
        check_media: bool = False
    ) -> Dict[str, List['Note']]:
        """Validate a batch of notes and categorize them.
        
        Args:
            notes: List of Note objects to validate
            check_media: Whether to also check media fields
            
        Returns:
            Dictionary with categorized notes:
            - 'needs_sync': Notes that need deep sync
            - 'complete': Notes with complete data
            - 'recent': Notes within 7*24 hours (subset of needs_sync)
            - 'missing_fields': Notes with missing fields (subset of needs_sync)
        """
        result = {
            'needs_sync': [],
            'complete': [],
            'recent': [],
            'missing_fields': [],
        }
        
        for note in notes:
            needs_sync, reasons = NoteValidator.needs_deep_sync(note)
            
            if needs_sync:
                result['needs_sync'].append(note)
                
                if 'recent_note_within_7d' in reasons:
                    result['recent'].append(note)
                else:
                    result['missing_fields'].append(note)
            else:
                # Check if fully complete (including media if requested)
                if NoteValidator.is_data_complete(note, check_media):
                    result['complete'].append(note)
                else:
                    # Has critical fields but missing media
                    result['needs_sync'].append(note)
                    result['missing_fields'].append(note)
        
        return result
    
    @staticmethod
    def get_all_missing_fields(note: 'Note') -> Dict[str, List[str]]:
        """Get all missing fields for a note, categorized by type.
        
        Args:
            note: Note object to check
            
        Returns:
            Dictionary with missing fields by category:
            - critical: Critical fields (upload_time, desc)
            - basic: Basic fields (type, title, nickname, etc.)
            - interaction: Interaction fields (liked_count, collected_count, etc.)
            - media: Media fields (cover_local, image_list, etc.)
        """
        return {
            'critical': NoteValidator.get_missing_critical_fields(note),
            'basic': NoteValidator.get_missing_basic_fields(note),
            'interaction': NoteValidator.get_missing_interaction_fields(note),
            'media': NoteValidator.get_missing_media_fields(note),
        }
    
    @staticmethod
    def get_validation_summary(notes: List['Note']) -> Dict:
        """Get validation summary for a batch of notes.
        
        Args:
            notes: List of Note objects to validate
            
        Returns:
            Summary dictionary with counts and details for all field categories
        """
        result = NoteValidator.validate_notes_batch(notes)
        
        # Initialize missing field counts for all table display fields
        missing_field_counts = {
            # Critical fields
            'upload_time': 0,
            'desc': 0,
            # Basic fields
            'type': 0,
            'title': 0,
            'nickname': 0,
            'avatar': 0,
            # Interaction fields
            'liked_count': 0,
            'collected_count': 0,
            'comment_count': 0,
            'share_count': 0,
            # Media fields
            'cover_remote': 0,
            'cover_local': 0,
            'image_list': 0,
            'video_addr': 0,
        }
        
        # Count missing fields across all notes (not just missing_fields category)
        for note in notes:
            all_missing = NoteValidator.get_all_missing_fields(note)
            
            # Count critical fields
            for field in all_missing['critical']:
                if field in missing_field_counts:
                    missing_field_counts[field] += 1
            
            # Count basic fields
            for field in all_missing['basic']:
                if field in missing_field_counts:
                    missing_field_counts[field] += 1
            
            # Count interaction fields
            for field in all_missing['interaction']:
                if field in missing_field_counts:
                    missing_field_counts[field] += 1
            
            # Count media fields
            for field in all_missing['media']:
                if field in missing_field_counts:
                    missing_field_counts[field] += 1
        
        # Calculate field completeness rates
        total_notes = len(notes)
        field_completeness = {}
        if total_notes > 0:
            for field, missing_count in missing_field_counts.items():
                complete_count = total_notes - missing_count
                field_completeness[field] = round((complete_count / total_notes) * 100, 1)
        
        return {
            'total': total_notes,
            'needs_sync': len(result['needs_sync']),
            'complete': len(result['complete']),
            'recent_notes': len(result['recent']),
            'missing_fields_notes': len(result['missing_fields']),
            'missing_field_counts': missing_field_counts,
            'field_completeness': field_completeness,
            # Legacy field name for backward compatibility
            'missing_field_details': missing_field_counts,
        }


class DeepSyncValidator:
    """Validator for deep sync operations.
    
    Performs validation:
    1. Before sync: Identify notes that need to be fetched
    2. After sync: Verify all notes have complete data
    """
    
    def __init__(self, account_id: int, user_id: str):
        """Initialize the validator.
        
        Args:
            account_id: Database ID of the account
            user_id: XHS user ID
        """
        self.account_id = account_id
        self.user_id = user_id
        self.pre_validation_result: Optional[Dict] = None
        self.post_validation_result: Optional[Dict] = None
    
    def pre_sync_validate(self, notes: List['Note']) -> Dict:
        """Validate notes before sync to identify what needs updating.
        
        Args:
            notes: List of existing Note objects
            
        Returns:
            Validation result with notes categorized
        """
        self.pre_validation_result = NoteValidator.validate_notes_batch(notes)
        
        summary = NoteValidator.get_validation_summary(notes)
        summary['validation_type'] = 'pre_sync'
        summary['account_id'] = self.account_id
        summary['user_id'] = self.user_id
        
        logger.info(
            f"[PreSyncValidation] Account {self.user_id}: "
            f"total={summary['total']}, needs_sync={summary['needs_sync']}, "
            f"complete={summary['complete']}, recent={summary['recent_notes']}, "
            f"missing_fields={summary['missing_fields_notes']}"
        )
        
        return summary
    
    def post_sync_validate(self, notes: List['Note']) -> Dict:
        """Validate notes after sync to verify data completeness.
        
        Args:
            notes: List of Note objects after sync
            
        Returns:
            Validation result with incomplete notes identified
        """
        self.post_validation_result = NoteValidator.validate_notes_batch(notes)
        
        summary = NoteValidator.get_validation_summary(notes)
        summary['validation_type'] = 'post_sync'
        summary['account_id'] = self.account_id
        summary['user_id'] = self.user_id
        
        # Calculate success rate
        if summary['total'] > 0:
            summary['completeness_rate'] = round(
                (summary['complete'] / summary['total']) * 100, 2
            )
        else:
            summary['completeness_rate'] = 100.0
        
        # Identify notes that still need sync
        incomplete_note_ids = [
            note.note_id for note in self.post_validation_result['needs_sync']
        ]
        summary['incomplete_note_ids'] = incomplete_note_ids[:50]  # Limit for logging
        summary['incomplete_count'] = len(incomplete_note_ids)
        
        logger.info(
            f"[PostSyncValidation] Account {self.user_id}: "
            f"total={summary['total']}, complete={summary['complete']}, "
            f"incomplete={summary['incomplete_count']}, "
            f"completeness_rate={summary['completeness_rate']}%"
        )
        
        if summary['incomplete_count'] > 0:
            logger.warning(
                f"[PostSyncValidation] Account {self.user_id} has {summary['incomplete_count']} "
                f"incomplete notes after sync. Missing fields: {summary['missing_field_details']}"
            )
        
        return summary
    
    def get_notes_needing_sync(self) -> List['Note']:
        """Get list of notes that need deep sync.
        
        Returns:
            List of Note objects that need to be fetched
        """
        if self.pre_validation_result:
            return self.pre_validation_result['needs_sync']
        return []
    
    def get_incomplete_notes(self) -> List['Note']:
        """Get list of notes that are still incomplete after sync.
        
        Returns:
            List of Note objects with incomplete data
        """
        if self.post_validation_result:
            return self.post_validation_result['needs_sync']
        return []


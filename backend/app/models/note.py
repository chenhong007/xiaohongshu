"""
笔记模型
"""
import json
from datetime import datetime
from ..extensions import db


class Note(db.Model):
    """笔记模型"""
    __tablename__ = 'notes'
    
    # Add indexes for common query patterns (排序、筛选、复合查询)
    __table_args__ = (
        # 复合索引：用户+时间、用户+类型（常用筛选组合）
        db.Index('ix_notes_user_upload_time', 'user_id', 'upload_time'),
        db.Index('ix_notes_user_type', 'user_id', 'type'),
        # 排序字段索引（点赞、收藏、评论、转发排序）
        db.Index('ix_notes_liked_count', 'liked_count'),
        db.Index('ix_notes_collected_count', 'collected_count'),
        db.Index('ix_notes_comment_count', 'comment_count'),
        db.Index('ix_notes_share_count', 'share_count'),
        # 性能优化：添加 last_updated 索引用于时间范围回退查询
        db.Index('ix_notes_last_updated', 'last_updated'),
        # 复合索引：类型+时间（按类型筛选后排序）
        db.Index('ix_notes_type_upload_time', 'type', 'upload_time'),
    )
    
    note_id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(db.String(64), db.ForeignKey('accounts.user_id'), index=True)
    
    # 基本信息
    nickname = db.Column(db.String(128))
    avatar = db.Column(db.String(512))
    title = db.Column(db.String(256))
    desc = db.Column(db.Text)
    type = db.Column(db.String(32), index=True)  # 图集 / 视频
    
    # 互动数据
    liked_count = db.Column(db.Integer, default=0)
    collected_count = db.Column(db.Integer, default=0)
    comment_count = db.Column(db.Integer, default=0)
    share_count = db.Column(db.Integer, default=0)
    
    # 媒体信息
    upload_time = db.Column(db.String(64), index=True)
    video_addr = db.Column(db.String(512))
    image_list = db.Column(db.Text)  # JSON 格式存储图片列表
    tags = db.Column(db.Text)  # JSON 格式存储标签
    ip_location = db.Column(db.String(64))
    # 预览封面：cover_remote 为远程首图/视频封面，cover_local 为本地缓存地址
    cover_remote = db.Column(db.String(512))
    cover_local = db.Column(db.String(512))
    
    # xsec_token: 笔记级别的验证token，用于获取笔记详情API
    xsec_token = db.Column(db.String(256))
    
    # 元数据
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_image_list(self):
        """获取图片列表"""
        if self.image_list:
            try:
                return json.loads(self.image_list)
            except:
                return []
        return []
    
    def get_tags(self):
        """获取标签列表"""
        if self.tags:
            try:
                return json.loads(self.tags)
            except:
                return []
        return []
    
    def to_dict(self, minimal: bool = False):
        """转换为字典
        
        Args:
            minimal: 如果为 True，只返回列表展示需要的核心字段（性能优化）
        """
        if minimal:
            # 列表页只需要这些字段，避免传输大量数据
            return {
                'note_id': self.note_id,
                'user_id': self.user_id,
                'nickname': self.nickname,
                'avatar': self.avatar,
                'title': self.title,
                'desc': self.desc[:200] if self.desc else None,  # 只返回前200字符
                'type': self.type,
                'liked_count': self.liked_count,
                'collected_count': self.collected_count,
                'comment_count': self.comment_count,
                'share_count': self.share_count,
                'upload_time': self.upload_time,
                'cover_remote': self.cover_remote,
                'cover_local': self.cover_local,
            }
        
        # 完整字段（详情页或导出使用）
        return {
            'note_id': self.note_id,
            'user_id': self.user_id,
            'nickname': self.nickname,
            'avatar': self.avatar,
            'title': self.title,
            'desc': self.desc,
            'type': self.type,
            'liked_count': self.liked_count,
            'collected_count': self.collected_count,
            'comment_count': self.comment_count,
            'share_count': self.share_count,
            'upload_time': self.upload_time,
            'video_addr': self.video_addr,
            'image_list': self.get_image_list(),
            'tags': self.get_tags(),
            'ip_location': self.ip_location,
            'cover_remote': self.cover_remote,
            'cover_local': self.cover_local,
            'xsec_token': self.xsec_token,
            'last_updated': (self.last_updated.isoformat() + 'Z') if self.last_updated else None,
        }
    
    def __repr__(self):
        return f'<Note {self.title}>'


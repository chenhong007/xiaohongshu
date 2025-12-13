"""
笔记模型
"""
import json
from datetime import datetime
from ..extensions import db


class Note(db.Model):
    """笔记模型"""
    __tablename__ = 'notes'
    
    # Add composite index for common query patterns
    __table_args__ = (
        db.Index('ix_notes_user_upload_time', 'user_id', 'upload_time'),
        db.Index('ix_notes_user_type', 'user_id', 'type'),
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
    
    def to_dict(self):
        """转换为字典"""
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
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
        }
    
    def __repr__(self):
        return f'<Note {self.title}>'


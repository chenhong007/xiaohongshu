"""
Cookie 存储模型
"""
from datetime import datetime
from ..extensions import db


class Cookie(db.Model):
    """Cookie 存储模型"""
    __tablename__ = 'cookies'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    cookie_str = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.String(64))  # 关联的用户ID
    nickname = db.Column(db.String(128))
    avatar = db.Column(db.String(512))
    is_active = db.Column(db.Boolean, default=True)
    is_valid = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_checked = db.Column(db.DateTime)
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'nickname': self.nickname,
            'avatar': self.avatar,
            'is_active': self.is_active,
            'is_valid': self.is_valid,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
        }
    
    def __repr__(self):
        return f'<Cookie {self.nickname}>'


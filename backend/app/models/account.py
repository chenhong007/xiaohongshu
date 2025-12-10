"""
账号模型
"""
from datetime import datetime
from ..extensions import db


class Account(db.Model):
    """博主账号模型"""
    __tablename__ = 'accounts'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128))
    avatar = db.Column(db.String(512))
    red_id = db.Column(db.String(64))  # 小红书号
    xsec_token = db.Column(db.String(256))  # xsec_token 用于API请求验证
    desc = db.Column(db.Text)  # 简介
    fans = db.Column(db.Integer, default=0)  # 粉丝数
    follows = db.Column(db.Integer, default=0)  # 关注数
    interaction = db.Column(db.Integer, default=0)  # 获赞与收藏
    
    # 同步状态
    last_sync = db.Column(db.DateTime)
    total_msgs = db.Column(db.Integer, default=0)
    loaded_msgs = db.Column(db.Integer, default=0)
    progress = db.Column(db.Integer, default=0)
    status = db.Column(db.String(32), default='pending')  # pending, processing, completed, failed
    error_message = db.Column(db.Text)  # 同步失败时的错误信息
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联笔记
    notes = db.relationship('Note', backref='account', lazy='dynamic')
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'avatar': self.avatar,
            'red_id': self.red_id,
            'xsec_token': self.xsec_token,
            'desc': self.desc,
            'fans': self.fans,
            'follows': self.follows,
            'interaction': self.interaction,
            'last_sync': self.last_sync.isoformat() + 'Z' if self.last_sync else None,
            'total_msgs': self.total_msgs,
            'loaded_msgs': self.loaded_msgs,
            'progress': self.progress,
            'status': self.status,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
        }
    
    def __repr__(self):
        return f'<Account {self.name}>'


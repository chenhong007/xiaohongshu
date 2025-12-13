"""
账号模型
"""
import json
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
    # xsec_token 已移除：用户级别的 token 现在每次同步时动态获取，笔记级别的 token 从 all_note_info 获取
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
    sync_heartbeat = db.Column(db.DateTime)  # 同步心跳时间，用于检测僵死任务
    
    # 同步日志 (JSON格式，存储深度同步过程中的详细异常信息)
    # 结构: {
    #   "sync_mode": "deep",
    #   "start_time": "2024-01-01T00:00:00",
    #   "end_time": "2024-01-01T00:05:00",
    #   "summary": {"total": 100, "success": 95, "rate_limited": 3, "failed": 2},
    #   "issues": [
    #     {"type": "rate_limited", "note_id": "xxx", "message": "访问频次异常", "time": "..."},
    #     {"type": "missing_field", "note_id": "xxx", "fields": ["upload_time"], "time": "..."},
    #     {"type": "fetch_failed", "note_id": "xxx", "message": "...", "time": "..."}
    #   ]
    # }
    sync_logs = db.Column(db.Text)  # JSON格式的同步日志
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联笔记
    notes = db.relationship('Note', backref='account', lazy='dynamic')
    
    def to_dict(self, include_full_logs=False):
        """转换为字典
        
        Args:
            include_full_logs: 是否包含完整的 sync_logs（包括 issues 列表）。
                              默认 False，只返回 summary 以减少数据传输量。
        """
        # Parse sync_logs JSON - only return summary by default
        sync_logs_data = None
        if self.sync_logs:
            try:
                full_logs = json.loads(self.sync_logs)
                if include_full_logs:
                    sync_logs_data = full_logs
                else:
                    # Only return summary without issues list
                    sync_logs_data = {
                        'sync_mode': full_logs.get('sync_mode'),
                        'start_time': full_logs.get('start_time'),
                        'end_time': full_logs.get('end_time'),
                        'summary': full_logs.get('summary'),
                        'issues_count': len(full_logs.get('issues', [])),
                    }
            except (json.JSONDecodeError, TypeError):
                sync_logs_data = None
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'avatar': self.avatar,
            'red_id': self.red_id,
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
            'sync_logs': sync_logs_data,
            'sync_heartbeat': self.sync_heartbeat.isoformat() + 'Z' if self.sync_heartbeat else None,
            'created_at': self.created_at.isoformat() + 'Z' if self.created_at else None,
        }
    
    def get_sync_logs_issues(self, page=1, page_size=50, issue_type=None):
        """分页获取同步日志的 issues 列表
        
        Args:
            page: 页码，从1开始
            page_size: 每页数量，默认50
            issue_type: 可选，筛选特定类型的问题
        
        Returns:
            dict: {issues: [], total: int, page: int, page_size: int, total_pages: int}
        """
        if not self.sync_logs:
            return {'issues': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0}
        
        try:
            full_logs = json.loads(self.sync_logs)
            all_issues = full_logs.get('issues', [])
            
            # Filter by type if specified
            if issue_type:
                all_issues = [i for i in all_issues if i.get('type') == issue_type]
            
            total = len(all_issues)
            total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
            
            # Paginate
            start = (page - 1) * page_size
            end = start + page_size
            paginated_issues = all_issues[start:end]
            
            return {
                'issues': paginated_issues,
                'total': total,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
            }
        except (json.JSONDecodeError, TypeError):
            return {'issues': [], 'total': 0, 'page': page, 'page_size': page_size, 'total_pages': 0}
    
    def __repr__(self):
        return f'<Account {self.name}>'


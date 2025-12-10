"""
Cookie 存储模型
支持加密存储
"""
from datetime import datetime
from ..extensions import db


class Cookie(db.Model):
    """
    Cookie 存储模型
    
    支持两种存储方式：
    1. 加密存储（推荐）：Cookie 存储在 encrypted_cookie 字段，使用 Fernet 加密
    2. 明文存储（后备）：Cookie 存储在 cookie_str 字段，仅用于开发环境
    
    使用 get_cookie_str() 和 set_cookie_str() 方法访问 Cookie，
    这些方法会自动处理加密/解密
    """
    __tablename__ = 'cookies'
    
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    
    # Cookie 存储字段
    # 保留 cookie_str 用于向后兼容和开发环境
    cookie_str = db.Column(db.Text, nullable=True)
    # 新增加密字段
    encrypted_cookie = db.Column(db.Text, nullable=True)
    
    # 用户信息
    user_id = db.Column(db.String(64))
    nickname = db.Column(db.String(128))
    avatar = db.Column(db.String(512))
    
    # 状态
    is_active = db.Column(db.Boolean, default=True)
    is_valid = db.Column(db.Boolean, default=True)
    
    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_checked = db.Column(db.DateTime)
    
    def get_cookie_str(self) -> str:
        """
        获取解密后的 Cookie 字符串
        
        优先从 encrypted_cookie 解密，如果失败则从 cookie_str 获取
        """
        # 优先使用加密存储
        if self.encrypted_cookie:
            try:
                from ..utils.crypto import decrypt_cookie
                decrypted = decrypt_cookie(self.encrypted_cookie)
                if decrypted:
                    return decrypted
            except Exception:
                pass
        
        # 后备：使用明文存储
        return self.cookie_str or ''
    
    def set_cookie_str(self, cookie_str: str) -> None:
        """
        设置 Cookie 字符串（自动加密）
        
        如果加密密钥可用，存储到 encrypted_cookie
        否则存储到 cookie_str（明文）
        """
        if not cookie_str:
            self.cookie_str = None
            self.encrypted_cookie = None
            return
        
        try:
            from ..utils.crypto import encrypt_cookie, get_crypto
            crypto = get_crypto()
            
            if crypto.is_secure:
                # 使用加密存储
                self.encrypted_cookie = encrypt_cookie(cookie_str)
                self.cookie_str = None  # 清除明文
            else:
                # 开发环境：使用混淆存储（不完全安全）
                self.encrypted_cookie = encrypt_cookie(cookie_str)
                # 同时保留明文用于调试（仅开发环境）
                self.cookie_str = cookie_str
        except Exception as e:
            # 加密失败，使用明文存储
            print(f"[Warning] Cookie encryption failed: {e}")
            self.cookie_str = cookie_str
            self.encrypted_cookie = None
    
    def to_dict(self):
        """
        转换为字典（不包含敏感的 Cookie 字符串）
        """
        return {
            'id': self.id,
            'user_id': self.user_id,
            'nickname': self.nickname,
            'avatar': self.avatar,
            'is_active': self.is_active,
            'is_valid': self.is_valid,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'has_encrypted': bool(self.encrypted_cookie),  # 指示是否加密存储
        }
    
    def __repr__(self):
        return f'<Cookie {self.nickname or self.user_id}>'

"""
加密工具模块
用于 Cookie 等敏感数据的加密存储
"""
import os
import base64
import hashlib
from typing import Optional

# 尝试导入 cryptography，如果不存在则使用简单的混淆方案
try:
    from cryptography.fernet import Fernet, InvalidToken
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False
    InvalidToken = Exception


class CookieCrypto:
    """
    Cookie 加密/解密工具
    
    使用 Fernet 对称加密（如果可用），否则使用简单的 XOR 混淆
    """
    
    def __init__(self, key: Optional[str] = None):
        """
        初始化加密工具
        
        Args:
            key: 加密密钥，如果不提供则从环境变量读取
        """
        self._key = key or os.environ.get('COOKIE_ENCRYPTION_KEY')
        self._fernet = None
        
        if HAS_CRYPTOGRAPHY and self._key:
            try:
                # 确保密钥是有效的 Fernet 密钥格式
                self._fernet = Fernet(self._key.encode() if isinstance(self._key, str) else self._key)
            except Exception as e:
                print(f"[Warning] Invalid Fernet key, falling back to simple obfuscation: {e}")
                self._fernet = None
    
    @property
    def is_secure(self) -> bool:
        """是否使用了安全加密"""
        return self._fernet is not None
    
    def encrypt(self, plaintext: str) -> str:
        """
        加密字符串
        
        Args:
            plaintext: 明文
            
        Returns:
            加密后的字符串（Base64 编码）
        """
        if not plaintext:
            return ''
        
        if self._fernet:
            # 使用 Fernet 加密
            encrypted = self._fernet.encrypt(plaintext.encode('utf-8'))
            return encrypted.decode('utf-8')
        else:
            # 使用简单混淆（不安全，仅用于开发环境）
            return self._simple_obfuscate(plaintext)
    
    def decrypt(self, ciphertext: str) -> str:
        """
        解密字符串
        
        Args:
            ciphertext: 密文
            
        Returns:
            解密后的明文
        """
        if not ciphertext:
            return ''
        
        if self._fernet:
            try:
                decrypted = self._fernet.decrypt(ciphertext.encode('utf-8'))
                return decrypted.decode('utf-8')
            except InvalidToken:
                # 可能是旧的未加密数据，直接返回
                return ciphertext
        else:
            # 尝试简单去混淆
            return self._simple_deobfuscate(ciphertext)
    
    def _simple_obfuscate(self, text: str) -> str:
        """简单混淆（不安全）"""
        # 添加前缀标记
        prefix = "OBF:"
        encoded = base64.b64encode(text.encode('utf-8')).decode('utf-8')
        return prefix + encoded
    
    def _simple_deobfuscate(self, text: str) -> str:
        """简单去混淆"""
        prefix = "OBF:"
        if text.startswith(prefix):
            try:
                encoded = text[len(prefix):]
                return base64.b64decode(encoded.encode('utf-8')).decode('utf-8')
            except Exception:
                return text
        return text
    
    @staticmethod
    def generate_key() -> str:
        """
        生成新的加密密钥
        
        Returns:
            Fernet 密钥字符串
        """
        if HAS_CRYPTOGRAPHY:
            return Fernet.generate_key().decode('utf-8')
        else:
            # 生成一个随机的 Base64 字符串作为后备
            import secrets
            return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8')


# 全局实例
_crypto_instance: Optional[CookieCrypto] = None


def get_crypto() -> CookieCrypto:
    """获取全局加密实例"""
    global _crypto_instance
    if _crypto_instance is None:
        _crypto_instance = CookieCrypto()
    return _crypto_instance


def encrypt_cookie(cookie_str: str) -> str:
    """加密 Cookie 字符串"""
    return get_crypto().encrypt(cookie_str)


def decrypt_cookie(encrypted: str) -> str:
    """解密 Cookie 字符串"""
    return get_crypto().decrypt(encrypted)


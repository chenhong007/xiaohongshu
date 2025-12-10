"""
加密工具模块
用于 Cookie 等敏感数据的加密存储和传输加密
"""
import os
import base64
import hashlib
import secrets
from typing import Optional, Tuple

# 尝试导入 cryptography，如果不存在则使用简单的混淆方案
try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
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


class TransportCrypto:
    """
    传输加密工具
    用于前后端之间的 Cookie 加密传输
    使用 AES-256-CBC 加密
    """
    
    def __init__(self, key: Optional[str] = None):
        """
        初始化传输加密工具
        
        Args:
            key: 32 字节的密钥（Base64 编码），如果不提供则从环境变量读取或生成
        """
        self._key_str = key or os.environ.get('TRANSPORT_ENCRYPTION_KEY')
        
        if self._key_str:
            try:
                self._key = base64.b64decode(self._key_str)
                if len(self._key) != 32:
                    raise ValueError("Key must be 32 bytes")
            except Exception:
                self._key = self._derive_key(self._key_str)
        else:
            # 生成一个会话密钥（每次重启会变化）
            self._key = secrets.token_bytes(32)
            self._key_str = base64.b64encode(self._key).decode('utf-8')
    
    def _derive_key(self, password: str) -> bytes:
        """从密码派生 32 字节密钥"""
        return hashlib.sha256(password.encode('utf-8')).digest()
    
    def get_public_key(self) -> str:
        """
        获取公钥（用于前端加密）
        注意：对于对称加密，这实际上是共享密钥
        生产环境建议使用 HTTPS 确保安全
        """
        return self._key_str
    
    def encrypt(self, plaintext: str) -> Tuple[str, str]:
        """
        加密字符串
        
        Returns:
            (密文 Base64, IV Base64)
        """
        if not plaintext:
            return '', ''
        
        if HAS_CRYPTOGRAPHY:
            iv = secrets.token_bytes(16)
            cipher = Cipher(algorithms.AES(self._key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            
            # PKCS7 填充
            padding_length = 16 - (len(plaintext.encode('utf-8')) % 16)
            padded_data = plaintext.encode('utf-8') + bytes([padding_length] * padding_length)
            
            encrypted = encryptor.update(padded_data) + encryptor.finalize()
            return base64.b64encode(encrypted).decode('utf-8'), base64.b64encode(iv).decode('utf-8')
        else:
            # 后备方案：简单 XOR + Base64
            return self._simple_encrypt(plaintext), ''
    
    def decrypt(self, ciphertext: str, iv: str = '') -> str:
        """
        解密字符串
        
        Args:
            ciphertext: 密文（Base64 编码）
            iv: 初始化向量（Base64 编码）
        """
        if not ciphertext:
            return ''
        
        if HAS_CRYPTOGRAPHY and iv:
            try:
                iv_bytes = base64.b64decode(iv)
                encrypted_bytes = base64.b64decode(ciphertext)
                
                cipher = Cipher(algorithms.AES(self._key), modes.CBC(iv_bytes), backend=default_backend())
                decryptor = cipher.decryptor()
                
                decrypted = decryptor.update(encrypted_bytes) + decryptor.finalize()
                
                # 移除 PKCS7 填充
                padding_length = decrypted[-1]
                return decrypted[:-padding_length].decode('utf-8')
            except Exception as e:
                print(f"[Warning] AES decryption failed: {e}")
                # 尝试简单解密
                return self._simple_decrypt(ciphertext)
        else:
            return self._simple_decrypt(ciphertext)
    
    def _simple_encrypt(self, text: str) -> str:
        """简单加密（后备方案）"""
        key_bytes = self._key
        text_bytes = text.encode('utf-8')
        result = bytes([text_bytes[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(text_bytes))])
        return 'XOR:' + base64.b64encode(result).decode('utf-8')
    
    def _simple_decrypt(self, text: str) -> str:
        """简单解密（后备方案）"""
        if text.startswith('XOR:'):
            try:
                encrypted = base64.b64decode(text[4:])
                key_bytes = self._key
                result = bytes([encrypted[i] ^ key_bytes[i % len(key_bytes)] for i in range(len(encrypted))])
                return result.decode('utf-8')
            except Exception:
                pass
        return text


# 全局传输加密实例
_transport_crypto_instance: Optional[TransportCrypto] = None


def get_transport_crypto() -> TransportCrypto:
    """获取全局传输加密实例"""
    global _transport_crypto_instance
    if _transport_crypto_instance is None:
        _transport_crypto_instance = TransportCrypto()
    return _transport_crypto_instance


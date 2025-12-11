"""
应用配置
支持从环境变量读取配置
"""
import os
import secrets

# 尝试加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 获取 backend 目录的绝对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    """基础配置"""
    
    # ==================== 安全配置 ====================
    # 使用环境变量或生成随机密钥（每次重启会变化）
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # Cookie 加密密钥
    COOKIE_ENCRYPTION_KEY = os.environ.get('COOKIE_ENCRYPTION_KEY')
    
    # 管理员 API Key
    ADMIN_API_KEY = os.environ.get('ADMIN_API_KEY')
    
    # ==================== 数据库配置 ====================
    # 支持从环境变量读取数据库 URL
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "xhs_data.db")}'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # ==================== CORS 配置 ====================
    # 允许的跨域来源（逗号分隔）
    CORS_ORIGINS = os.environ.get(
        'CORS_ORIGINS', 
        'http://localhost:5173,http://127.0.0.1:5173'
    ).split(',')
    
    # ==================== 数据存储路径 ====================
    MEDIA_PATH = os.path.join(BASE_DIR, 'datas', 'media_datas')
    EXCEL_PATH = os.path.join(BASE_DIR, 'datas', 'excel_datas')
    
    # ==================== 日志配置 ====================
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE')  # 可选的日志文件路径
    
    # ==================== 同步配置 ====================
    # 同步请求间隔（秒）
    SYNC_REQUEST_DELAY = float(os.environ.get('SYNC_REQUEST_DELAY', '1.0'))
    # 深度同步随机延迟区间（秒）
    # 【重要】小红书反爬策略很严格，延迟必须足够长！
    # 参考 fix_deep_sync.py 策略: 5-15秒基础延迟 + 20%概率额外暂停(最长30秒)
    DEEP_SYNC_DELAY_MIN = float(os.environ.get('DEEP_SYNC_DELAY_MIN', '5.0'))
    DEEP_SYNC_DELAY_MAX = float(os.environ.get('DEEP_SYNC_DELAY_MAX', '15.0'))
    # 额外随机长延迟的概率与上限（防爬虫抖动）
    DEEP_SYNC_EXTRA_PAUSE_CHANCE = float(os.environ.get('DEEP_SYNC_EXTRA_PAUSE_CHANCE', '0.20'))
    DEEP_SYNC_EXTRA_PAUSE_MAX = float(os.environ.get('DEEP_SYNC_EXTRA_PAUSE_MAX', '30.0'))
    # 最大并发同步数
    MAX_CONCURRENT_SYNCS = int(os.environ.get('MAX_CONCURRENT_SYNCS', '3'))
    
    @staticmethod
    def init_paths():
        """初始化数据目录"""
        for path in [Config.MEDIA_PATH, Config.EXCEL_PATH]:
            if not os.path.exists(path):
                os.makedirs(path)
    
    @classmethod
    def get_cors_config(cls):
        """获取 CORS 配置"""
        return {
            "origins": cls.CORS_ORIGINS,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "X-API-Key", "Authorization"],
            "supports_credentials": True,
        }


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True
    LOG_LEVEL = 'DEBUG'


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False
    LOG_LEVEL = 'WARNING'
    
    @classmethod
    def validate(cls):
        """验证生产环境必要配置"""
        errors = []
        
        if not os.environ.get('SECRET_KEY'):
            errors.append('SECRET_KEY 环境变量未设置')
        
        if not os.environ.get('COOKIE_ENCRYPTION_KEY'):
            errors.append('COOKIE_ENCRYPTION_KEY 环境变量未设置（Cookie 将以不安全方式存储）')
        
        if errors:
            print("⚠️ 生产环境配置警告:")
            for error in errors:
                print(f"  - {error}")


class TestingConfig(Config):
    """测试环境配置"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'


# 配置映射
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}


def get_config():
    """根据环境变量获取配置类"""
    env = os.environ.get('FLASK_ENV', 'development')
    return config.get(env, config['default'])

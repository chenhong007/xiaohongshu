"""
应用配置
"""
import os
import secrets

# 获取 backend 目录的绝对路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Config:
    """基础配置"""
    # 使用随机生成的密钥（每次重启会变化）或从环境变量读取
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    
    # 数据库配置
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(BASE_DIR, "xhs_data.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # 数据存储路径
    MEDIA_PATH = os.path.join(BASE_DIR, 'datas', 'media_datas')
    EXCEL_PATH = os.path.join(BASE_DIR, 'datas', 'excel_datas')
    
    @staticmethod
    def init_paths():
        """初始化数据目录"""
        for path in [Config.MEDIA_PATH, Config.EXCEL_PATH]:
            if not os.path.exists(path):
                os.makedirs(path)


class DevelopmentConfig(Config):
    """开发环境配置"""
    DEBUG = True


class ProductionConfig(Config):
    """生产环境配置"""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

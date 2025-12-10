"""
应用入口
小红书采集系统 - 后端服务

启动方式:
    python run.py

环境变量配置:
    - 复制 env.example 为 .env
    - 根据需要修改配置值
"""
import sys
import os

# 添加 backend 目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import create_app
from app.config import Config, get_config

# 初始化数据目录
Config.init_paths()

# 获取配置类
config_class = get_config()

# 创建应用实例
app = create_app(config_class)

if __name__ == '__main__':
    # 在生产环境验证配置
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        config_class.validate()
    
    print("=" * 60)
    print("🍓 小红书采集系统 - 后端服务")
    print("=" * 60)
    print(f"📌 服务地址: http://localhost:8000")
    print(f"📌 API 地址: http://localhost:8000/api/v1")
    print(f"📌 环境: {env}")
    print(f"📌 数据库: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"📌 CORS 允许来源: {', '.join(config_class.CORS_ORIGINS)}")
    
    # 检查安全配置
    from app.utils.crypto import get_crypto
    crypto = get_crypto()
    if crypto.is_secure:
        print("🔒 Cookie 加密: 已启用")
    else:
        print("⚠️  Cookie 加密: 未启用 (请设置 COOKIE_ENCRYPTION_KEY)")
    
    if os.environ.get('ADMIN_API_KEY'):
        print("🔒 管理员认证: 已启用")
    else:
        print("⚠️  管理员认证: 未启用 (请设置 ADMIN_API_KEY)")
    
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=8000, debug=(env == 'development'), use_reloader=False)

"""
应用入口
小红书采集系统 - 后端服务

启动方式:
    python run.py              # 普通模式
    python run.py --websocket  # WebSocket 模式（推荐）

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

from app import create_app, WEBSOCKET_AVAILABLE, socketio
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
    
    # Check if WebSocket mode is requested
    use_websocket = '--websocket' in sys.argv or os.environ.get('USE_WEBSOCKET', '').lower() in ('1', 'true', 'yes')
    
    print("=" * 60)
    print("🍓 小红书采集系统 - 后端服务")
    print("=" * 60)
    print(f"📌 服务地址: http://localhost:8000")
    print(f"📌 API 地址: http://localhost:8000/api/v1")
    print(f"📌 环境: {env}")
    print(f"📌 数据库: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print(f"📌 CORS 允许来源: {', '.join(config_class.CORS_ORIGINS)}")
    
    # WebSocket status
    if WEBSOCKET_AVAILABLE and use_websocket:
        print("🔌 WebSocket 推送: 已启用 (实时同步进度)")
    elif WEBSOCKET_AVAILABLE:
        print("🔌 WebSocket 推送: 可用 (使用 --websocket 启用)")
    else:
        print("⚠️  WebSocket 推送: 不可用 (请安装 flask-socketio 和 eventlet)")
    
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
    
    if WEBSOCKET_AVAILABLE and use_websocket:
        # Run with WebSocket support using eventlet
        print("🚀 使用 SocketIO + Eventlet 运行...")
        socketio.run(app, host='0.0.0.0', port=8000, debug=(env == 'development'))
    else:
        # Run with standard Flask development server
        app.run(host='0.0.0.0', port=8000, debug=(env == 'development'), use_reloader=False)

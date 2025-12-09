"""
应用入口
"""
import sys
import os

# 添加 backend 目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.config import Config

# 初始化数据目录
Config.init_paths()

# 创建应用实例
app = create_app()

if __name__ == '__main__':
    print("=" * 50)
    print("小红书采集系统 - 后端服务")
    print("=" * 50)
    print(f"服务地址: http://localhost:8000")
    print(f"数据库路径: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print("=" * 50)
    
    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=False)


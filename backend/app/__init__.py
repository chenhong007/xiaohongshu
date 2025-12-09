"""
Flask 应用工厂
"""
import sqlite3
from flask import Flask
from flask_cors import CORS

from .config import Config
from .extensions import db
from .api import accounts_bp, notes_bp, auth_bp, search_bp


def migrate_database(db_path):
    """检查并添加缺失的数据库列"""
    import os
    if not os.path.exists(db_path):
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 检查 accounts 表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
        if not cursor.fetchone():
            conn.close()
            return
        
        # 获取现有列
        cursor.execute("PRAGMA table_info(accounts)")
        existing_columns = [row[1] for row in cursor.fetchall()]
        
        # 需要添加的列
        columns_to_add = {
            'red_id': 'VARCHAR(64)',
            'desc': 'TEXT',
            'fans': 'INTEGER DEFAULT 0',
            'follows': 'INTEGER DEFAULT 0',
            'interaction': 'INTEGER DEFAULT 0',
            'last_sync': 'DATETIME',
            'total_msgs': 'INTEGER DEFAULT 0',
            'loaded_msgs': 'INTEGER DEFAULT 0',
            'progress': 'INTEGER DEFAULT 0',
            'status': "VARCHAR(32) DEFAULT 'pending'",
            'created_at': 'DATETIME',
            'updated_at': 'DATETIME',
        }
        
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE accounts ADD COLUMN {column_name} {column_type}")
                    print(f"[迁移] 添加列 accounts.{column_name}")
                except sqlite3.OperationalError:
                    pass
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[迁移] 数据库迁移检查失败: {e}")


def create_app(config_class=Config):
    """创建并配置 Flask 应用"""
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # 初始化扩展
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_app(app)
    
    # 注册蓝图
    app.register_blueprint(accounts_bp, url_prefix='/api')
    app.register_blueprint(notes_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(search_bp, url_prefix='/api')
    
    # 数据库迁移检查（在 create_all 之前）
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
        migrate_database(db_path)
    
    # 创建数据库表
    with app.app_context():
        db.create_all()
    
    # 注册错误处理
    register_error_handlers(app)
    
    return app


def register_error_handlers(app):
    """注册全局错误处理"""
    
    @app.errorhandler(400)
    def bad_request(error):
        return {'error': 'Bad Request', 'message': str(error.description)}, 400
    
    @app.errorhandler(404)
    def not_found(error):
        return {'error': 'Not Found', 'message': str(error.description)}, 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return {'error': 'Internal Server Error', 'message': '服务器内部错误'}, 500


"""
Flask 应用工厂
"""
import os
import sqlite3
from flask import Flask
from flask_cors import CORS

from .config import Config, get_config
from .extensions import db
from .api import accounts_bp, notes_bp, auth_bp, search_bp
from .utils.logger import setup_logger, get_logger


def migrate_database(db_path):
    """检查并添加缺失的数据库列"""
    if not os.path.exists(db_path):
        return
    
    logger = get_logger('migration')
    
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
            'xsec_token': 'VARCHAR(256)',
            'desc': 'TEXT',
            'fans': 'INTEGER DEFAULT 0',
            'follows': 'INTEGER DEFAULT 0',
            'interaction': 'INTEGER DEFAULT 0',
            'last_sync': 'DATETIME',
            'total_msgs': 'INTEGER DEFAULT 0',
            'loaded_msgs': 'INTEGER DEFAULT 0',
            'progress': 'INTEGER DEFAULT 0',
            'status': "VARCHAR(32) DEFAULT 'pending'",
            'error_message': 'TEXT',
            'created_at': 'DATETIME',
            'updated_at': 'DATETIME',
        }
        
        for column_name, column_type in columns_to_add.items():
            if column_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE accounts ADD COLUMN {column_name} {column_type}")
                    logger.info(f"添加列 accounts.{column_name}")
                except sqlite3.OperationalError:
                    pass

        # 检查 notes 表，补充本地/远程封面字段和xsec_token
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notes'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(notes)")
            notes_columns = [row[1] for row in cursor.fetchall()]
            note_columns_to_add = {
                'cover_remote': 'VARCHAR(512)',
                'cover_local': 'VARCHAR(512)',
                'xsec_token': 'VARCHAR(256)',  # 笔记级别的验证token
            }
            for column_name, column_type in note_columns_to_add.items():
                if column_name not in notes_columns:
                    try:
                        cursor.execute(f"ALTER TABLE notes ADD COLUMN {column_name} {column_type}")
                        logger.info(f"添加列 notes.{column_name}")
                    except sqlite3.OperationalError:
                        pass
        
        # 检查 cookies 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cookies'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(cookies)")
            cookie_columns = [row[1] for row in cursor.fetchall()]
            
            cookie_columns_to_add = {
                'encrypted_cookie': 'TEXT',  # 新增加密字段
            }
            
            for column_name, column_type in cookie_columns_to_add.items():
                if column_name not in cookie_columns:
                    try:
                        cursor.execute(f"ALTER TABLE cookies ADD COLUMN {column_name} {column_type}")
                        logger.info(f"添加列 cookies.{column_name}")
                    except sqlite3.OperationalError:
                        pass
        
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"数据库迁移检查失败: {e}")


def create_app(config_class=None):
    """创建并配置 Flask 应用"""
    # 如果没有指定配置，根据环境变量自动选择
    if config_class is None:
        config_class = get_config()
    
    app = Flask(__name__)
    app.config.from_object(config_class)
    # 确保数据目录存在（媒体/导出等）
    Config.init_paths()
    
    # 初始化日志
    setup_logger(
        log_level=app.config.get('LOG_LEVEL', 'INFO'),
        log_file=app.config.get('LOG_FILE')
    )
    
    logger = get_logger('app')
    
    # 初始化 CORS（使用配置的域名列表）
    cors_config = config_class.get_cors_config()
    CORS(app, resources={r"/api/*": cors_config})
    
    # 初始化数据库扩展
    db.init_app(app)
    
    # 注册蓝图
    # 保持向后兼容，同时支持 /api 和 /api/v1
    app.register_blueprint(accounts_bp, url_prefix='/api')
    app.register_blueprint(notes_bp, url_prefix='/api')
    app.register_blueprint(auth_bp, url_prefix='/api')
    app.register_blueprint(search_bp, url_prefix='/api')
    
    # API v1 版本（推荐使用）
    app.register_blueprint(accounts_bp, url_prefix='/api/v1', name='accounts_v1')
    app.register_blueprint(notes_bp, url_prefix='/api/v1', name='notes_v1')
    app.register_blueprint(auth_bp, url_prefix='/api/v1', name='auth_v1')
    app.register_blueprint(search_bp, url_prefix='/api/v1', name='search_v1')
    
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
    
    # 注册请求钩子
    register_request_hooks(app)
    
    # 注册健康检查端点
    register_health_check(app)
    
    logger.info(f"应用初始化完成，数据库: {db_uri}")
    
    return app


def register_error_handlers(app):
    """注册全局错误处理"""
    from .utils.responses import ApiResponse
    
    @app.errorhandler(400)
    def bad_request(error):
        return ApiResponse.error(
            str(error.description) if hasattr(error, 'description') else '请求参数错误',
            400, 'BAD_REQUEST'
        )
    
    @app.errorhandler(404)
    def not_found(error):
        return ApiResponse.not_found(
            str(error.description) if hasattr(error, 'description') else '资源不存在'
        )
    
    @app.errorhandler(405)
    def method_not_allowed(error):
        return ApiResponse.error('请求方法不允许', 405, 'METHOD_NOT_ALLOWED')
    
    @app.errorhandler(500)
    def internal_error(error):
        logger = get_logger('error')
        logger.exception(error)
        return ApiResponse.server_error('服务器内部错误')


def register_request_hooks(app):
    """注册请求钩子"""
    import time
    from flask import g, request
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
    
    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            duration = (time.time() - g.start_time) * 1000
            # 可以在这里记录请求日志
            if duration > 1000:  # 记录慢请求
                logger = get_logger('slow_request')
                logger.warning(f"Slow request: {request.method} {request.path} took {duration:.2f}ms")
        return response


def register_health_check(app):
    """注册健康检查端点"""
    from flask import jsonify
    
    @app.route('/api/health')
    @app.route('/api/v1/health')
    def health_check():
        """健康检查端点，用于 Docker 容器健康检查"""
        return jsonify({
            'status': 'healthy',
            'service': 'xhs-backend'
        })
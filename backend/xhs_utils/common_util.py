import os
import sqlite3
from loguru import logger


def get_db_path():
    """获取数据库路径"""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'xhs_data.db')


def get_active_cookie():
    """从数据库获取当前激活的 Cookie"""
    try:
        db_path = get_db_path()
        if not os.path.exists(db_path):
            logger.warning(f"Database not found at {db_path}")
            return None
            
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 获取激活的且有效的 cookie
        cursor.execute('''
            SELECT cookie_str FROM cookies 
            WHERE is_active = 1 AND is_valid = 1 
            ORDER BY updated_at DESC 
            LIMIT 1
        ''')
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row['cookie_str']
        return None
    except Exception as e:
        logger.error(f"Error getting cookie from database: {e}")
        return None


def save_cookie_to_db(cookies_str, user_id=None, nickname=None, avatar=None):
    """保存 Cookie 到数据库"""
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 确保 cookies 表存在
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS cookies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cookie_str TEXT NOT NULL,
                user_id TEXT,
                nickname TEXT,
                avatar TEXT,
                is_active INTEGER DEFAULT 1,
                is_valid INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_checked TIMESTAMP
            )
        ''')
        
        # 将所有现有的 cookie 设置为非激活
        cursor.execute('UPDATE cookies SET is_active = 0')
        
        # 检查是否已存在相同 user_id 的 cookie
        if user_id:
            cursor.execute('SELECT id FROM cookies WHERE user_id = ?', (user_id,))
            existing = cursor.fetchone()
            
            if existing:
                # 更新现有记录
                cursor.execute('''
                    UPDATE cookies 
                    SET cookie_str = ?, nickname = ?, avatar = ?, is_active = 1, is_valid = 1, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                ''', (cookies_str, nickname, avatar, user_id))
            else:
                # 插入新记录
                cursor.execute('''
                    INSERT INTO cookies (cookie_str, user_id, nickname, avatar, is_active, is_valid)
                    VALUES (?, ?, ?, ?, 1, 1)
                ''', (cookies_str, user_id, nickname, avatar))
        else:
            # 没有 user_id，直接插入新记录
            cursor.execute('''
                INSERT INTO cookies (cookie_str, user_id, nickname, avatar, is_active, is_valid)
                VALUES (?, ?, ?, ?, 1, 1)
            ''', (cookies_str, user_id, nickname, avatar))
        
        conn.commit()
        conn.close()
        logger.info(f"Successfully saved cookie to database")
        return True
    except Exception as e:
        logger.error(f"Error saving cookie to database: {e}")
        return False


def init():
    """初始化：创建必要目录并获取 Cookie"""
    media_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/media_datas'))
    excel_base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../datas/excel_datas'))
    for base_path in [media_base_path, excel_base_path]:
        if not os.path.exists(base_path):
            os.makedirs(base_path)
            logger.info(f'创建目录 {base_path}')
    
    # 从数据库获取 Cookie
    cookies_str = get_active_cookie()
    
    base_path = {
        'media': media_base_path,
        'excel': excel_base_path,
    }
    return cookies_str, base_path

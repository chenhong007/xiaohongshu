"""
数据库迁移脚本 - 添加缺失的列和修复表结构
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'xhs_data.db')

def get_existing_columns(cursor, table_name):
    """获取表的现有列"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]

def table_exists(cursor, table_name):
    """检查表是否存在"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None

def migrate():
    """执行迁移"""
    print(f"连接数据库: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print("数据库文件不存在，无需迁移")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # ==================== 迁移 accounts 表 ====================
        if table_exists(cursor, 'accounts'):
            existing_columns = get_existing_columns(cursor, 'accounts')
            print(f"accounts 表现有列: {existing_columns}")
            
            # 需要添加的列定义
            accounts_columns = {
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
            
            for column_name, column_type in accounts_columns.items():
                if column_name not in existing_columns:
                    print(f"添加列 accounts.{column_name}")
                    try:
                        cursor.execute(f"ALTER TABLE accounts ADD COLUMN {column_name} {column_type}")
                        print(f"  ✓ 成功")
                    except sqlite3.OperationalError as e:
                        print(f"  ✗ 失败: {e}")
        
        # ==================== 迁移 notes 表 ====================
        print("\n检查 notes 表...")
        
        if table_exists(cursor, 'notes'):
            existing_columns = get_existing_columns(cursor, 'notes')
            print(f"notes 表现有列: {existing_columns}")
            
            # 检查是否缺少关键列 note_id
            if 'note_id' not in existing_columns:
                print("notes 表结构不正确，需要重建...")
                # 备份旧数据（如果有的话）
                cursor.execute("SELECT * FROM notes")
                old_data = cursor.fetchall()
                print(f"  备份了 {len(old_data)} 条旧数据")
                
                # 删除旧表
                cursor.execute("DROP TABLE notes")
                print("  ✓ 已删除旧的 notes 表")
                
                # 创建新表
                cursor.execute('''
                    CREATE TABLE notes (
                        note_id VARCHAR(64) PRIMARY KEY,
                        user_id VARCHAR(64),
                        nickname VARCHAR(128),
                        avatar VARCHAR(512),
                        title VARCHAR(256),
                        "desc" TEXT,
                        type VARCHAR(32),
                        liked_count INTEGER DEFAULT 0,
                        collected_count INTEGER DEFAULT 0,
                        comment_count INTEGER DEFAULT 0,
                        share_count INTEGER DEFAULT 0,
                        upload_time VARCHAR(64),
                        video_addr VARCHAR(512),
                        image_list TEXT,
                        tags TEXT,
                        ip_location VARCHAR(64),
                        last_updated DATETIME,
                        FOREIGN KEY (user_id) REFERENCES accounts(user_id)
                    )
                ''')
                print("  ✓ 已创建新的 notes 表")
                
                # 创建索引
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_notes_user_id ON notes(user_id)")
                print("  ✓ 已创建索引")
        else:
            print("notes 表不存在，将由 SQLAlchemy 自动创建")
        
        conn.commit()
        print("\n迁移完成！")
        
        # 显示迁移后的表结构
        if table_exists(cursor, 'accounts'):
            print("\n迁移后的 accounts 表结构:")
            cursor.execute("PRAGMA table_info(accounts)")
            for row in cursor.fetchall():
                print(f"  {row[1]}: {row[2]}")
        
        if table_exists(cursor, 'notes'):
            print("\n迁移后的 notes 表结构:")
            cursor.execute("PRAGMA table_info(notes)")
            for row in cursor.fetchall():
                print(f"  {row[1]}: {row[2]}")
            
    except Exception as e:
        print(f"迁移失败: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()


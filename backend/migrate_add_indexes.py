"""
数据库迁移脚本 - 添加性能优化索引
解决问题: 缺少对 upload_time、type 等常用筛选字段的索引
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'xhs_data.db')


def get_existing_indexes(cursor, table_name):
    """获取表的现有索引"""
    cursor.execute(f"PRAGMA index_list({table_name})")
    return [row[1] for row in cursor.fetchall()]


def table_exists(cursor, table_name):
    """检查表是否存在"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None


def create_index_if_not_exists(cursor, index_name, table_name, columns):
    """创建索引（如果不存在）"""
    columns_str = ', '.join(columns)
    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({columns_str})")
        print(f"  ✓ 索引 {index_name} 创建成功")
        return True
    except sqlite3.OperationalError as e:
        print(f"  ✗ 索引 {index_name} 创建失败: {e}")
        return False


def migrate():
    """执行索引迁移"""
    print(f"连接数据库: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print("数据库文件不存在，无需迁移")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # ==================== 为 notes 表添加索引 ====================
        print("\n检查 notes 表索引...")
        
        if table_exists(cursor, 'notes'):
            existing_indexes = get_existing_indexes(cursor, 'notes')
            print(f"notes 表现有索引: {existing_indexes}")
            
            # 需要创建的索引
            indexes_to_create = [
                # Single column indexes for common filter/sort operations
                ('ix_notes_type', 'notes', ['type']),
                ('ix_notes_upload_time', 'notes', ['upload_time']),
                # Composite indexes for common query patterns
                ('ix_notes_user_upload_time', 'notes', ['user_id', 'upload_time']),
                ('ix_notes_user_type', 'notes', ['user_id', 'type']),
            ]
            
            for index_name, table_name, columns in indexes_to_create:
                if index_name not in existing_indexes:
                    print(f"添加索引 {index_name} ({', '.join(columns)})")
                    create_index_if_not_exists(cursor, index_name, table_name, columns)
                else:
                    print(f"  - 索引 {index_name} 已存在，跳过")
        else:
            print("notes 表不存在，跳过索引创建")
        
        conn.commit()
        print("\n索引迁移完成！")
        
        # 显示迁移后的索引
        if table_exists(cursor, 'notes'):
            print("\n迁移后的 notes 表索引:")
            cursor.execute("PRAGMA index_list(notes)")
            for row in cursor.fetchall():
                index_name = row[1]
                cursor.execute(f"PRAGMA index_info({index_name})")
                columns = [col[2] for col in cursor.fetchall()]
                print(f"  {index_name}: ({', '.join(columns)})")
            
    except Exception as e:
        print(f"迁移失败: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()


if __name__ == '__main__':
    migrate()

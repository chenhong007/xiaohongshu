"""
修复脚本：为现有笔记填充 cover_remote 字段
从 image_list 中提取第一张图片作为封面
"""
import sqlite3
import os
import json

DB_PATH = os.path.join(os.path.dirname(__file__), 'xhs_data.db')

def fix_cover_data():
    """修复笔记的封面数据"""
    print(f"连接数据库: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print("数据库文件不存在")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 查找所有 cover_remote 为空但 image_list 有数据的笔记
        cursor.execute("""
            SELECT note_id, image_list, type 
            FROM notes 
            WHERE (cover_remote IS NULL OR cover_remote = '') 
              AND image_list IS NOT NULL 
              AND image_list != '' 
              AND image_list != '[]'
        """)
        
        notes_to_fix = cursor.fetchall()
        print(f"找到 {len(notes_to_fix)} 条需要修复封面的笔记")
        
        fixed_count = 0
        for note_id, image_list_json, note_type in notes_to_fix:
            try:
                image_list = json.loads(image_list_json)
                if image_list and len(image_list) > 0:
                    cover_remote = image_list[0]
                    cursor.execute(
                        "UPDATE notes SET cover_remote = ? WHERE note_id = ?",
                        (cover_remote, note_id)
                    )
                    fixed_count += 1
            except (json.JSONDecodeError, IndexError, TypeError) as e:
                print(f"  跳过笔记 {note_id}: {e}")
                continue
        
        conn.commit()
        print(f"✓ 成功修复 {fixed_count} 条笔记的封面数据")
        
        # 统计修复后的状态
        cursor.execute("SELECT COUNT(*) FROM notes WHERE cover_remote IS NOT NULL AND cover_remote != ''")
        with_cover = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM notes")
        total = cursor.fetchone()[0]
        
        print(f"\n修复后统计:")
        print(f"  总笔记数: {total}")
        print(f"  有封面数: {with_cover}")
        print(f"  无封面数: {total - with_cover}")
        
    except Exception as e:
        print(f"修复失败: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_cover_data()


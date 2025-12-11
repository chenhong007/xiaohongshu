"""
修复脚本：为视频类型笔记批量更新封面数据
通过重新解析列表页数据，提取视频封面
"""
import sqlite3
import os
import json
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

DB_PATH = os.path.join(os.path.dirname(__file__), 'xhs_data.db')

def fix_video_cover():
    """
    问题说明：
    视频类型的笔记在列表页 API 返回时，封面存储在 cover.url_default 或 cover.info_list 中
    但 handle_note_info 将其存储到 video_cover 字段，而不是 image_list
    导致 cover_remote 计算时无法从 image_list 中获取
    
    解决方案：
    由于数据库中没有原始的 API 响应数据，我们需要重新同步
    但作为临时方案，我们可以标记这些笔记需要重新获取详情
    """
    print(f"连接数据库: {DB_PATH}")
    
    if not os.path.exists(DB_PATH):
        print("数据库文件不存在")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # 统计视频笔记中缺少封面的数量
        cursor.execute("""
            SELECT COUNT(*) FROM notes 
            WHERE type = '视频' 
              AND (cover_remote IS NULL OR cover_remote = '')
        """)
        video_no_cover = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM notes 
            WHERE type = '视频' 
              AND (video_addr IS NULL OR video_addr = '')
        """)
        video_no_addr = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM notes WHERE type = '视频'")
        total_video = cursor.fetchone()[0]
        
        print(f"\n视频笔记统计:")
        print(f"  总视频笔记数: {total_video}")
        print(f"  缺少封面数: {video_no_cover}")
        print(f"  缺少视频地址数: {video_no_addr}")
        
        # 对于缺少封面的视频，清空 upload_time 以触发深度同步重新获取详情
        # 这是一个技巧：深度同步会检查 upload_time 是否为空来决定是否获取详情
        print(f"\n准备标记 {video_no_cover} 条视频笔记需要重新同步...")
        
        cursor.execute("""
            UPDATE notes 
            SET upload_time = '' 
            WHERE type = '视频' 
              AND (cover_remote IS NULL OR cover_remote = '')
        """)
        
        conn.commit()
        print(f"✓ 已标记 {cursor.rowcount} 条笔记需要重新同步")
        print(f"\n请重新执行深度同步以获取完整的视频封面数据")
        
    except Exception as e:
        print(f"修复失败: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    fix_video_cover()


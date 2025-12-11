#!/usr/bin/env python3
"""
修复缺失封面和发布时间的笔记
通过重新获取笔记详情来补全数据
"""
import os
import sys
import time
import random

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import Note, Account, Cookie
from app.services.sync_service import SyncService
from xhs_utils.data_util import handle_note_info

def get_cookie_str():
    """获取有效的Cookie字符串"""
    cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if cookie:
        return cookie.get_cookie_str()
    return None

def fix_notes_for_user(user_id, max_notes=None, dry_run=False):
    """修复指定用户的笔记数据"""
    from apis.xhs_pc_apis import XHS_Apis
    
    xhs_apis = XHS_Apis()
    cookie_str = get_cookie_str()
    
    if not cookie_str:
        print("错误：未找到有效的Cookie")
        return
    
    # 查询缺失数据的笔记
    query = Note.query.filter(
        Note.user_id == user_id,
        db.or_(
            Note.cover_remote.is_(None),
            Note.cover_remote == '',
            Note.upload_time.is_(None),
            Note.upload_time == ''
        )
    )
    
    notes_to_fix = query.all()
    total = len(notes_to_fix)
    
    print(f"用户 {user_id} 有 {total} 条笔记需要修复")
    
    if max_notes:
        notes_to_fix = notes_to_fix[:max_notes]
        print(f"本次处理前 {len(notes_to_fix)} 条")
    
    if dry_run:
        print("【干运行模式】不会实际修改数据")
        for note in notes_to_fix[:10]:
            print(f"  - {note.note_id}: {note.title}, type={note.type}, cover_remote={note.cover_remote or '空'}")
        return
    
    # 获取账号的 xsec_token
    account = Account.query.filter_by(user_id=user_id).first()
    xsec_token = account.xsec_token if account else ''
    
    fixed_count = 0
    failed_count = 0
    
    for idx, note in enumerate(notes_to_fix):
        print(f"\n[{idx+1}/{len(notes_to_fix)}] 处理笔记: {note.note_id} - {note.title}")
        
        # 构建笔记URL
        note_url = f"https://www.xiaohongshu.com/explore/{note.note_id}?xsec_token={xsec_token}"
        
        # 获取笔记详情
        success, msg, note_detail = xhs_apis.get_note_info(note_url, cookie_str)
        
        print(f"  API返回: success={success}, msg={msg}")
        if note_detail:
            print(f"  note_detail keys: {list(note_detail.keys()) if isinstance(note_detail, dict) else 'not a dict'}")
            data = note_detail.get('data') if isinstance(note_detail, dict) else None
            if data:
                print(f"  data keys: {list(data.keys())}")
                items = data.get('items', [])
                print(f"  items count: {len(items) if items else 0}")
        
        if not success:
            print(f"  获取详情失败: {msg}")
            failed_count += 1
            time.sleep(random.uniform(1, 2))
            continue
        
        if success and note_detail:
            try:
                data = note_detail.get('data')
                if data and data.get('items') and len(data['items']) > 0:
                    note_data = data['items'][0]
                    note_data['url'] = note_url
                    cleaned_data = handle_note_info(note_data, from_list=False)
                    
                    # 更新笔记数据
                    SyncService._save_note(cleaned_data, download_media=True)
                    fixed_count += 1
                    print(f"  ✓ 修复成功")
                    print(f"    - upload_time: {cleaned_data.get('upload_time')}")
                    print(f"    - video_cover: {cleaned_data.get('video_cover', '')[:50]}...")
                else:
                    print(f"  详情数据为空")
                    failed_count += 1
            except Exception as e:
                print(f"  解析错误: {e}")
                failed_count += 1
        
        # 随机延迟，避免被封
        delay = random.uniform(0.8, 1.8)
        if random.random() < 0.1:
            delay += random.uniform(0.5, 3)
        time.sleep(delay)
    
    print(f"\n===== 修复完成 =====")
    print(f"成功: {fixed_count}")
    print(f"失败: {failed_count}")

def show_stats():
    """显示统计信息"""
    total_notes = Note.query.count()
    missing_cover_remote = Note.query.filter(
        db.or_(Note.cover_remote.is_(None), Note.cover_remote == '')
    ).count()
    missing_cover_local = Note.query.filter(
        db.or_(Note.cover_local.is_(None), Note.cover_local == '')
    ).count()
    missing_upload_time = Note.query.filter(
        db.or_(Note.upload_time.is_(None), Note.upload_time == '')
    ).count()
    
    print(f"===== 笔记数据统计 =====")
    print(f"总笔记数: {total_notes}")
    print(f"缺少 cover_remote: {missing_cover_remote}")
    print(f"缺少 cover_local: {missing_cover_local}")
    print(f"缺少 upload_time: {missing_upload_time}")
    
    # 按用户统计
    print(f"\n===== 按用户统计（缺失数据 Top 10）=====")
    results = db.session.query(
        Note.user_id,
        db.func.count(Note.note_id).label('missing_count')
    ).filter(
        db.or_(
            Note.cover_remote.is_(None),
            Note.cover_remote == '',
            Note.upload_time.is_(None),
            Note.upload_time == ''
        )
    ).group_by(Note.user_id).order_by(db.desc('missing_count')).limit(10).all()
    
    for user_id, count in results:
        account = Account.query.filter_by(user_id=user_id).first()
        name = account.name if account else '未知'
        print(f"  {name} ({user_id}): {count} 条")

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        import argparse
        parser = argparse.ArgumentParser(description='修复缺失封面和发布时间的笔记')
        parser.add_argument('--user-id', type=str, help='指定用户ID')
        parser.add_argument('--max', type=int, help='最多处理多少条笔记')
        parser.add_argument('--dry-run', action='store_true', help='只显示将要处理的数据，不实际修改')
        parser.add_argument('--stats', action='store_true', help='显示统计信息')
        
        args = parser.parse_args()
        
        if args.stats:
            show_stats()
        elif args.user_id:
            fix_notes_for_user(args.user_id, max_notes=args.max, dry_run=args.dry_run)
        else:
            print("请指定 --user-id 或 --stats")
            print("示例:")
            print("  python fix_missing_covers_deep.py --stats")
            print("  python fix_missing_covers_deep.py --user-id 59757acd50c4b45e6e9a90df --dry-run")
            print("  python fix_missing_covers_deep.py --user-id 59757acd50c4b45e6e9a90df --max 10")


#!/usr/bin/env python3
"""
批量修复缺失封面的脚本
1. 为有 cover_remote 但没有 cover_local 的笔记下载封面
2. 为没有 cover_remote 但有 image_list 的笔记从图片列表中提取并下载封面
"""
import os
import sys
import time
import json
import requests

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import Note
from app.extensions import db
from app.config import Config
from Spider_XHS.xhs_utils.xhs_util import get_common_headers


def fix_missing_covers(limit=None, dry_run=False, mode='all'):
    """
    修复缺失的封面图片
    
    Args:
        limit: 最多处理多少条（None=全部）
        dry_run: 仅预览不实际下载
        mode: 修复模式 (all=全部, remote=只修复有cover_remote的, image=只修复需要从image_list提取的)
    """
    app = create_app()
    with app.app_context():
        Config.init_paths()
        
        notes_to_fix = []
        
        # 1. 查找有 cover_remote 但没有 cover_local 的笔记
        if mode in ['all', 'remote']:
            remote_notes = Note.query.filter(
                Note.cover_remote.isnot(None),
                Note.cover_remote != '',
                (Note.cover_local.is_(None) | (Note.cover_local == ''))
            ).all()
            for note in remote_notes:
                notes_to_fix.append({
                    'note': note,
                    'source': 'cover_remote',
                    'url': note.cover_remote
                })
            print(f"从 cover_remote 修复: {len(remote_notes)} 条")
        
        # 2. 查找没有 cover_remote 但有 image_list 的笔记
        if mode in ['all', 'image']:
            image_notes = Note.query.filter(
                (Note.cover_remote.is_(None) | (Note.cover_remote == '')),
                (Note.cover_local.is_(None) | (Note.cover_local == '')),
                Note.image_list.isnot(None),
                Note.image_list != '',
                Note.image_list != '[]'
            ).all()
            for note in image_notes:
                try:
                    img_list = json.loads(note.image_list)
                    if img_list and len(img_list) > 0:
                        notes_to_fix.append({
                            'note': note,
                            'source': 'image_list',
                            'url': img_list[0]
                        })
                except:
                    pass
            print(f"从 image_list 修复: {len([n for n in notes_to_fix if n['source'] == 'image_list'])} 条")
        
        if limit:
            notes_to_fix = notes_to_fix[:limit]
        
        total = len(notes_to_fix)
        print(f"\n总共需要修复: {total} 条笔记")
        
        if dry_run:
            print("\n[预览模式] 以下笔记将被修复:")
            for i, item in enumerate(notes_to_fix[:30]):
                note = item['note']
                print(f"  {i+1}. [{item['source']}] {note.note_id}: {note.title[:30] if note.title else '无标题'}...")
            if total > 30:
                print(f"  ... 还有 {total - 30} 条")
            return
        
        if total == 0:
            print("没有需要修复的笔记")
            return
        
        headers = get_common_headers()
        success_count = 0
        fail_count = 0
        
        for idx, item in enumerate(notes_to_fix):
            note = item['note']
            remote_url = item['url']
            source = item['source']
            
            try:
                note_id = note.note_id
                
                # 生成本地文件名
                ext = '.jpg'
                filename = f"{note_id}_cover{ext}"
                filepath = os.path.join(Config.MEDIA_PATH, filename)
                
                # 检查是否已存在
                if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                    # 文件存在，只需更新数据库
                    note.cover_local = f"/api/media/{filename}"
                    if source == 'image_list' and not note.cover_remote:
                        note.cover_remote = remote_url
                    db.session.commit()
                    success_count += 1
                    print(f"[{idx+1}/{total}] ✓ 已存在: {note_id}")
                    continue
                
                # 下载封面
                print(f"[{idx+1}/{total}] 下载中 [{source}]: {note_id}...", end=" ")
                resp = requests.get(remote_url, headers=headers, stream=True, timeout=15)
                
                if resp.status_code == 200:
                    with open(filepath, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            if chunk:
                                f.write(chunk)
                    
                    # 验证文件大小
                    if os.path.getsize(filepath) < 1024:
                        os.remove(filepath)
                        fail_count += 1
                        print("✗ 文件太小")
                        continue
                    
                    # 更新数据库
                    note.cover_local = f"/api/media/{filename}"
                    if source == 'image_list' and not note.cover_remote:
                        note.cover_remote = remote_url
                    db.session.commit()
                    success_count += 1
                    print("✓ 成功")
                else:
                    fail_count += 1
                    print(f"✗ 失败 ({resp.status_code})")
                
                # 避免请求过快
                time.sleep(0.3)
                
            except Exception as e:
                fail_count += 1
                print(f"✗ 错误: {e}")
                db.session.rollback()
        
        print(f"\n修复完成: 成功 {success_count}, 失败 {fail_count}")


def show_stats():
    """显示当前封面统计"""
    app = create_app()
    with app.app_context():
        import sqlite3
        from sqlalchemy import text
        
        total = Note.query.count()
        with_cover_local = Note.query.filter(
            Note.cover_local.isnot(None),
            Note.cover_local != ''
        ).count()
        with_cover_remote = Note.query.filter(
            Note.cover_remote.isnot(None),
            Note.cover_remote != ''
        ).count()
        
        # 检查可修复的数量
        fixable_from_remote = Note.query.filter(
            Note.cover_remote.isnot(None),
            Note.cover_remote != '',
            (Note.cover_local.is_(None) | (Note.cover_local == ''))
        ).count()
        
        fixable_from_image = Note.query.filter(
            (Note.cover_remote.is_(None) | (Note.cover_remote == '')),
            (Note.cover_local.is_(None) | (Note.cover_local == '')),
            Note.image_list.isnot(None),
            Note.image_list != '',
            Note.image_list != '[]'
        ).count()
        
        print("=" * 50)
        print("封面统计")
        print("=" * 50)
        print(f"总笔记数:              {total}")
        print(f"有本地封面:            {with_cover_local}")
        print(f"有远程封面URL:         {with_cover_remote}")
        print("-" * 50)
        print(f"可从cover_remote修复:  {fixable_from_remote}")
        print(f"可从image_list修复:    {fixable_from_image}")
        print(f"总计可修复:            {fixable_from_remote + fixable_from_image}")
        print("=" * 50)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='修复缺失的封面图片')
    parser.add_argument('--limit', type=int, help='最多处理多少条')
    parser.add_argument('--dry-run', action='store_true', help='仅预览不实际下载')
    parser.add_argument('--mode', choices=['all', 'remote', 'image'], default='all',
                        help='修复模式: all=全部, remote=只修复有cover_remote的, image=只从image_list提取')
    parser.add_argument('--stats', action='store_true', help='只显示统计信息')
    args = parser.parse_args()
    
    if args.stats:
        show_stats()
    else:
        fix_missing_covers(limit=args.limit, dry_run=args.dry_run, mode=args.mode)

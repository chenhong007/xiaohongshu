#!/usr/bin/env python3
"""
修复缺失封面和发布时间的笔记
通过重新获取笔记详情来补全数据

支持：
- 修复所有用户的所有数据
- 断点续传（记录进度）
- 批量处理
"""
import os
import sys
import time
import random
import json
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import Note, Account, Cookie
from app.services.sync_service import SyncService
from xhs_utils.data_util import handle_note_info

# 进度文件
PROGRESS_FILE = 'fix_progress.json'

def get_cookie_str():
    """获取有效的Cookie字符串"""
    cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if cookie:
        return cookie.get_cookie_str()
    return None

def load_progress():
    """加载进度"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {'processed_note_ids': [], 'last_user_id': None, 'stats': {'success': 0, 'failed': 0, 'skipped': 0}}

def save_progress(progress):
    """保存进度"""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)

def fix_notes_for_user(user_id, xhs_apis, cookie_str, progress, max_notes=None, min_delay=2.5, max_delay=5.0):
    """修复指定用户的笔记数据"""
    
    # 查询缺失数据的笔记（排除已处理的）
    processed_ids = set(progress['processed_note_ids'])
    
    query = Note.query.filter(
        Note.user_id == user_id,
        db.or_(
            Note.cover_remote.is_(None),
            Note.cover_remote == '',
            Note.upload_time.is_(None),
            Note.upload_time == ''
        )
    )
    
    # 排除已处理的笔记
    if processed_ids:
        query = query.filter(~Note.note_id.in_(processed_ids))
    
    notes_to_fix = query.all()
    total = len(notes_to_fix)
    
    if total == 0:
        return 0, 0, 0
    
    if max_notes:
        notes_to_fix = notes_to_fix[:max_notes]
    
    # 获取账号的 xsec_token
    account = Account.query.filter_by(user_id=user_id).first()
    xsec_token = account.xsec_token if account else ''
    account_name = account.name if account else user_id
    
    print(f"\n处理博主: {account_name} ({user_id}), 待修复: {total} 条")
    
    fixed_count = 0
    failed_count = 0
    skipped_count = 0
    
    for idx, note in enumerate(notes_to_fix):
        note_id = note.note_id
        
        # 检查是否已经处理过
        if note_id in processed_ids:
            skipped_count += 1
            continue
        
        print(f"  [{idx+1}/{len(notes_to_fix)}] {note_id} - {note.title[:30] if note.title else '无标题'}...", end=' ')
        
        # 构建笔记URL
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}"
        
        # 带重试的详情获取
        detail_saved = False
        rate_limited = False
        
        for retry_attempt in range(3):
            if retry_attempt > 0:
                wait_time = random.uniform(3, 6) * retry_attempt
                print(f"重试({retry_attempt+1}/3)...", end=' ')
                time.sleep(wait_time)
            
            success, msg, note_detail = xhs_apis.get_note_info(note_url, cookie_str)
            
            # 检查是否被限流或笔记不可用
            is_rate_limited = '频次异常' in str(msg) or '频繁操作' in str(msg)
            is_unavailable = '暂时无法浏览' in str(msg) or '笔记不存在' in str(msg)
            
            if is_rate_limited:
                rate_limited = True
                continue  # 重试
            
            if is_unavailable:
                print(f"不可用: {msg}")
                break  # 不重试
            
            if not success:
                print(f"失败: {msg}")
                break

            if success and note_detail:
                try:
                    data = note_detail.get('data')
                    if data and data.get('items') and len(data['items']) > 0:
                        note_data = data['items'][0]
                        note_data['url'] = note_url
                        cleaned_data = handle_note_info(note_data, from_list=False)
                        SyncService._save_note(cleaned_data, download_media=True)
                        detail_saved = True
                        print("✓ 成功")
                        break
                    else:
                        if '频次' in str(msg) or '频繁' in str(msg):
                            rate_limited = True
                            continue
                        print(f"数据为空: {msg}")
                        break
                except Exception as e:
                    print(f"解析错误: {e}")
                    break
        
        # 记录已处理
        progress['processed_note_ids'].append(note_id)
        
        if detail_saved:
            fixed_count += 1
            progress['stats']['success'] += 1
        else:
            failed_count += 1
            progress['stats']['failed'] += 1
        
        # 每处理10条保存一次进度
        if (idx + 1) % 10 == 0:
            save_progress(progress)
        
        # 如果限流，增加额外等待
        if rate_limited:
            extra_wait = random.uniform(8, 15)
            print(f"  限流检测，等待 {extra_wait:.1f}s...")
            time.sleep(extra_wait)
        else:
            # 正常延迟
            delay = random.uniform(min_delay, max_delay)
            if random.random() < 0.15:
                delay += random.uniform(2, 5)
            time.sleep(delay)
    
    # 保存进度
    save_progress(progress)
    
    return fixed_count, failed_count, skipped_count

def fix_all_users(max_notes_per_user=None, min_delay=2.5, max_delay=5.0, resume=True):
    """修复所有用户的笔记数据"""
    from apis.xhs_pc_apis import XHS_Apis
    
    xhs_apis = XHS_Apis()
    cookie_str = get_cookie_str()
    
    if not cookie_str:
        print("错误：未找到有效的Cookie")
        return
    
    # 加载进度
    progress = load_progress() if resume else {'processed_note_ids': [], 'last_user_id': None, 'stats': {'success': 0, 'failed': 0, 'skipped': 0}}
    
    # 获取所有有缺失数据的用户
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
    ).group_by(Note.user_id).order_by(db.desc('missing_count')).all()
    
    total_users = len(results)
    print(f"===== 开始修复所有用户数据 =====")
    print(f"共 {total_users} 个用户需要处理")
    print(f"已处理笔记数: {len(progress['processed_note_ids'])}")
    print(f"历史统计: 成功={progress['stats']['success']}, 失败={progress['stats']['failed']}")
    print(f"延迟设置: {min_delay}-{max_delay}秒")
    if max_notes_per_user:
        print(f"每用户最多处理: {max_notes_per_user} 条")
    print()
    
    total_fixed = 0
    total_failed = 0
    
    for user_idx, (user_id, missing_count) in enumerate(results):
        # 如果是恢复模式，跳过已处理的用户
        if resume and progress.get('last_user_id'):
            if user_id != progress['last_user_id']:
                # 检查这个用户是否还有未处理的笔记
                remaining = Note.query.filter(
                    Note.user_id == user_id,
                    ~Note.note_id.in_(progress['processed_note_ids']),
                    db.or_(
                        Note.cover_remote.is_(None),
                        Note.cover_remote == '',
                        Note.upload_time.is_(None),
                        Note.upload_time == ''
                    )
                ).count()
                if remaining == 0:
                    continue
        
        progress['last_user_id'] = user_id
        
        account = Account.query.filter_by(user_id=user_id).first()
        account_name = account.name if account else user_id
        
        print(f"\n[{user_idx+1}/{total_users}] ========== {account_name} ==========")
        
        try:
            fixed, failed, skipped = fix_notes_for_user(
                user_id, xhs_apis, cookie_str, progress,
                max_notes=max_notes_per_user,
                min_delay=min_delay,
                max_delay=max_delay
            )
            total_fixed += fixed
            total_failed += failed
            
            print(f"  本用户: 成功={fixed}, 失败={failed}, 跳过={skipped}")
            
        except KeyboardInterrupt:
            print("\n\n用户中断，保存进度...")
            save_progress(progress)
            break
        except Exception as e:
            print(f"  处理出错: {e}")
            save_progress(progress)
            continue
        
        # 用户之间额外等待
        if user_idx < total_users - 1:
            wait = random.uniform(5, 10)
            print(f"  等待 {wait:.1f}s 后处理下一个用户...")
            time.sleep(wait)
    
    # 最终保存进度
    save_progress(progress)
    
    print(f"\n===== 修复完成 =====")
    print(f"本次成功: {total_fixed}")
    print(f"本次失败: {total_failed}")
    print(f"总计成功: {progress['stats']['success']}")
    print(f"总计失败: {progress['stats']['failed']}")

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
    print(f"\n===== 按用户统计（缺失数据 Top 20）=====")
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
    ).group_by(Note.user_id).order_by(db.desc('missing_count')).limit(20).all()
    
    for user_id, count in results:
        account = Account.query.filter_by(user_id=user_id).first()
        name = account.name if account else '未知'
        print(f"  {name} ({user_id}): {count} 条")
    
    # 检查进度文件
    if os.path.exists(PROGRESS_FILE):
        progress = load_progress()
        print(f"\n===== 进度文件 =====")
        print(f"已处理笔记数: {len(progress['processed_note_ids'])}")
        print(f"上次处理用户: {progress.get('last_user_id', '无')}")
        print(f"累计成功: {progress['stats']['success']}")
        print(f"累计失败: {progress['stats']['failed']}")

def reset_progress():
    """重置进度"""
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
        print("进度已重置")
    else:
        print("没有进度文件")

if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        import argparse
        parser = argparse.ArgumentParser(description='修复缺失封面和发布时间的笔记')
        parser.add_argument('--user-id', type=str, help='指定用户ID（不指定则处理所有用户）')
        parser.add_argument('--max', type=int, help='每个用户最多处理多少条笔记')
        parser.add_argument('--min-delay', type=float, default=2.5, help='最小延迟秒数（默认2.5）')
        parser.add_argument('--max-delay', type=float, default=5.0, help='最大延迟秒数（默认5.0）')
        parser.add_argument('--no-resume', action='store_true', help='不使用断点续传，从头开始')
        parser.add_argument('--stats', action='store_true', help='显示统计信息')
        parser.add_argument('--reset', action='store_true', help='重置进度')
        parser.add_argument('--dry-run', action='store_true', help='只显示将要处理的数据，不实际修改')
        
        args = parser.parse_args()
        
        if args.stats:
            show_stats()
        elif args.reset:
            reset_progress()
        elif args.dry_run:
            # 显示将要处理的数据
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
            ).group_by(Note.user_id).order_by(db.desc('missing_count')).all()
            
            total = sum(count for _, count in results)
            print(f"【干运行模式】")
            print(f"将处理 {len(results)} 个用户，共 {total} 条笔记")
            print(f"预计时间: {total * 3.5 / 60:.1f} 分钟 （按平均3.5秒/条计算）")
        elif args.user_id:
            # 处理单个用户
            from apis.xhs_pc_apis import XHS_Apis
            xhs_apis = XHS_Apis()
            cookie_str = get_cookie_str()
            if cookie_str:
                progress = load_progress() if not args.no_resume else {'processed_note_ids': [], 'last_user_id': None, 'stats': {'success': 0, 'failed': 0, 'skipped': 0}}
                fix_notes_for_user(args.user_id, xhs_apis, cookie_str, progress, max_notes=args.max, min_delay=args.min_delay, max_delay=args.max_delay)
            else:
                print("错误：未找到有效的Cookie")
        else:
            # 处理所有用户
            fix_all_users(
                max_notes_per_user=args.max,
                min_delay=args.min_delay,
                max_delay=args.max_delay,
                resume=not args.no_resume
            )

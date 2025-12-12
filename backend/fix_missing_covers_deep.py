#!/usr/bin/env python3
"""
修复缺失封面或发布时间的笔记
默认使用列表页数据快速补封面；开启 --detail 时会尝试获取详情，
以补齐发布时间、完整图片列表等深度字段。

支持：
- 修复所有用户的所有数据
- 断点续传（记录进度）
- 批量处理
- 可选的详情模式用于补齐发布时间等深度字段
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
from Spider_XHS.xhs_utils.data_util import handle_note_info

# 进度文件
PROGRESS_FILE = 'fix_progress.json'


def build_missing_condition(include_upload_time=False):
    """构建需要修复的字段条件"""
    conditions = [
        Note.cover_remote.is_(None),
        Note.cover_remote == '',
        Note.cover_local.is_(None),
        Note.cover_local == ''
    ]
    if include_upload_time:
        conditions.extend([
            Note.upload_time.is_(None),
            Note.upload_time == ''
        ])
    return db.or_(*conditions)


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

def fix_notes_for_user(user_id, xhs_apis, cookie_str, progress, max_notes=None,
                       min_delay=2.5, max_delay=5.0, detail_mode=False,
                       include_upload_time=False):
    """修复指定用户的笔记数据
    
    修复策略：
    1. 默认模式（detail_mode=False）：仅使用列表页数据修复封面，不尝试获取详情
       - 速度快，不受API限流影响
       - 可以修复封面，但无法修复发布时间和完整图片列表
    
    2. 详情模式（detail_mode=True）：尝试获取每个笔记的详情
       - 速度慢，容易被限流
       - 可以获取完整数据，但成功率低
    
    当 include_upload_time=True 时，会额外扫描 upload_time 为空的笔记，
    该选项仅在详情模式下启用，用于补齐发布时间等深度字段。
    """
    
    # 查询缺失数据的笔记ID（排除已处理的）
    processed_ids = set(progress['processed_note_ids'])
    
    missing_condition = build_missing_condition(include_upload_time)
    query = Note.query.filter(
        Note.user_id == user_id,
        missing_condition
    )
    
    # 排除已处理的笔记
    if processed_ids:
        query = query.filter(~Note.note_id.in_(processed_ids))
    
    notes_to_fix_ids = set(n.note_id for n in query.all())
    total = len(notes_to_fix_ids)
    
    if total == 0:
        return 0, 0, 0
    
    # 获取账号
    account = Account.query.filter_by(user_id=user_id).first()
    account_name = account.name if account else user_id
    
    target_desc = "封面 + 发布时间" if include_upload_time else "封面"
    print(f"\n处理博主: {account_name} ({user_id}), 待修复{target_desc}: {total} 条")
    
    # 刷新用户的 xsec_token
    print(f"  正在刷新 xsec_token...")
    
    try:
        success_token, msg_token, fetched_token = xhs_apis.get_user_xsec_token(user_id, cookie_str)
        if success_token and fetched_token:
            xsec_token = fetched_token
            if account:
                account.xsec_token = xsec_token
                db.session.commit()
            print(f"  ✓ xsec_token 已刷新")
        else:
            xsec_token = account.xsec_token if account else ''
    except Exception as e:
        xsec_token = account.xsec_token if account else ''
    
    time.sleep(random.uniform(0.5, 1))
    
    # 获取用户的笔记列表
    user_url = f'https://www.xiaohongshu.com/user/profile/{user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
    
    print(f"  正在获取笔记列表...")
    success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookie_str)
    
    if not success or not all_note_info:
        print(f"  ✗ 获取笔记列表失败: {msg}")
        return 0, 0, 0
    
    print(f"  ✓ 获取到 {len(all_note_info)} 条笔记信息")
    
    # 建立 note -> xsec_token 映射，避免后续缺少 token
    note_token_map = {}
    for raw_note in all_note_info or []:
        nid = raw_note.get('note_id') or raw_note.get('id')
        n_token = raw_note.get('xsec_token')
        if nid and n_token:
            note_token_map[nid] = n_token
    
    # 过滤出需要修复的笔记
    notes_to_process = []
    for note_info in all_note_info:
        nid = note_info.get('note_id') or note_info.get('id')
        if nid and nid in notes_to_fix_ids and nid not in processed_ids:
            notes_to_process.append(note_info)
    
    if max_notes:
        notes_to_process = notes_to_process[:max_notes]
    
    print(f"  将处理 {len(notes_to_process)} 条需要修复的笔记")
    
    fixed_count = 0
    failed_count = 0
    skipped_count = 0
    
    for idx, note_info in enumerate(notes_to_process):
        note_id = note_info.get('note_id') or note_info.get('id')
        note_title = note_info.get('display_title') or note_info.get('title') or '无标题'
        
        # 检查是否已经处理过
        if note_id in processed_ids:
            skipped_count += 1
            continue
        
        print(f"  [{idx+1}/{len(notes_to_process)}] {note_id} - {note_title[:30]}...", end=' ')
        
        # 使用 handle_note_info 处理列表页/详情数据，传入笔记级 xsec_token
        note_xsec_token = note_info.get('xsec_token') or note_token_map.get(note_id) or xsec_token
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
        if note_xsec_token:
            note_url = f"{note_url}?xsec_token={note_xsec_token}&xsec_source=pc_search"
        
        def save_with_list_data():
            cleaned = handle_note_info(note_info, from_list=True, xsec_token=note_xsec_token)
            SyncService._save_note(cleaned, download_media=False)
        
        try:
            detail_done = False
            if detail_mode:
                # 尝试获取详情补齐发布时间/图片列表
                for retry in range(2):
                    if retry > 0:
                        wait = random.uniform(min_delay, max_delay)
                        time.sleep(wait)
                    detail_success, detail_msg, note_detail = xhs_apis.get_note_info(note_url, cookie_str)
                    if not detail_success:
                        if any(k in str(detail_msg) for k in ['xsec_token', '签名', '参数错误']):
                            # token 失效，放弃详情模式，后续使用列表数据兜底
                            break
                        continue
                    data = (note_detail or {}).get('data', {})
                    items = data.get('items') or []
                    if not items:
                        continue
                    cleaned_detail = handle_note_info(items[0], from_list=False, xsec_token=note_xsec_token)
                    SyncService._save_note(cleaned_detail, download_media=False)
                    detail_done = True
                    break
            
            if not detail_done:
                save_with_list_data()
            
            fixed_count += 1
            progress['stats']['success'] += 1
            print("✓ 深度字段已更新" if detail_done else "✓ 封面已更新")
        except Exception as e:
            failed_count += 1
            progress['stats']['failed'] += 1
            print(f"✗ 失败: {e}")
        
        # 记录已处理
        progress['processed_note_ids'].append(note_id)
        
        # 每处理50条保存一次进度
        if (idx + 1) % 50 == 0:
            save_progress(progress)
            print(f"    [进度已保存: 成功={fixed_count}, 失败={failed_count}]")
        
        # 短暂延迟（封面下载本身就需要时间）
        time.sleep(random.uniform(0.1, 0.3))
    
    # 保存进度
    save_progress(progress)
    
    return fixed_count, failed_count, skipped_count

def fix_all_users(max_notes_per_user=None, resume=True, detail_mode=False):
    """修复所有用户的笔记数据（可选详情模式）"""
    from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
    
    xhs_apis = XHS_Apis()
    cookie_str = get_cookie_str()
    
    if not cookie_str:
        print("错误：未找到有效的Cookie")
        return
    
    # 加载进度
    progress = load_progress() if resume else {'processed_note_ids': [], 'last_user_id': None, 'stats': {'success': 0, 'failed': 0, 'skipped': 0}}
    
    missing_condition = build_missing_condition(detail_mode)

    # 获取所有有缺失数据的用户
    results = db.session.query(
        Note.user_id,
        db.func.count(Note.note_id).label('missing_count')
    ).filter(
        missing_condition
    ).group_by(Note.user_id).order_by(db.desc('missing_count')).all()
    
    total_users = len(results)
    total_notes = sum(count for _, count in results)
    
    target_desc = "封面 + 发布时间" if detail_mode else "封面"
    print(f"===== 开始修复所有用户{target_desc}数据 =====")
    print(f"共 {total_users} 个用户，{total_notes} 条笔记需要处理")
    print(f"已处理笔记数: {len(progress['processed_note_ids'])}")
    print(f"历史统计: 成功={progress['stats']['success']}, 失败={progress['stats']['failed']}")
    if max_notes_per_user:
        print(f"每用户最多处理: {max_notes_per_user} 条")
    print()
    
    total_fixed = 0
    total_failed = 0
    
    for user_idx, (user_id, missing_count) in enumerate(results):
        # 如果是恢复模式，跳过已完全处理的用户
        if resume and progress.get('last_user_id'):
            # 检查这个用户是否还有未处理的笔记
            remaining = Note.query.filter(
                Note.user_id == user_id,
                ~Note.note_id.in_(progress['processed_note_ids']),
                missing_condition
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
                detail_mode=detail_mode,
                include_upload_time=detail_mode
            )
            total_fixed += fixed
            total_failed += failed
            
            print(f"  本用户完成: 成功={fixed}, 失败={failed}, 跳过={skipped}")
            
        except KeyboardInterrupt:
            print("\n\n用户中断，保存进度...")
            save_progress(progress)
            break
        except Exception as e:
            print(f"  处理出错: {e}")
            import traceback
            traceback.print_exc()
            save_progress(progress)
            continue
        
        # 用户之间短暂等待
        if user_idx < total_users - 1:
            wait = random.uniform(1, 2)
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
    
    # 计算需要修复封面的数量（cover_remote 或 cover_local 任一为空）
    need_fix_cover = Note.query.filter(
        db.or_(
            Note.cover_remote.is_(None),
            Note.cover_remote == '',
            Note.cover_local.is_(None),
            Note.cover_local == ''
        )
    ).count()
    
    print(f"===== 笔记数据统计 =====")
    print(f"总笔记数: {total_notes}")
    print(f"缺少 cover_remote: {missing_cover_remote}")
    print(f"缺少 cover_local: {missing_cover_local}")
    print(f"缺少 upload_time: {missing_upload_time}")
    print(f"需要修复封面: {need_fix_cover}")
    
    # 按用户统计（缺少封面）
    print(f"\n===== 按用户统计（缺失封面 Top 20）=====")
    results = db.session.query(
        Note.user_id,
        db.func.count(Note.note_id).label('missing_count')
    ).filter(
        db.or_(
            Note.cover_remote.is_(None),
            Note.cover_remote == '',
            Note.cover_local.is_(None),
            Note.cover_local == ''
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
        parser = argparse.ArgumentParser(
            description='修复缺失封面/发布时间的笔记（默认列表页，可配合 --detail 补齐深度字段）'
        )
        parser.add_argument('--user-id', type=str, help='指定用户ID（不指定则处理所有用户）')
        parser.add_argument('--max', type=int, help='每个用户最多处理多少条笔记')
        parser.add_argument('--no-resume', action='store_true', help='不使用断点续传，从头开始')
        parser.add_argument('--stats', action='store_true', help='显示统计信息')
        parser.add_argument('--reset', action='store_true', help='重置进度')
        parser.add_argument('--dry-run', action='store_true', help='只显示将要处理的数据，不实际修改')
        parser.add_argument(
            '--detail',
            action='store_true',
            help='开启详情模式：补齐发布时间/图集/互动等深度字段，并扫描 upload_time 为空的笔记'
        )
        
        args = parser.parse_args()
        
        if args.stats:
            show_stats()
        elif args.reset:
            reset_progress()
        elif args.dry_run:
            # 显示将要处理的数据
            target_desc = "封面 + 发布时间" if args.detail else "封面"
            missing_condition = build_missing_condition(args.detail)
            results = db.session.query(
                Note.user_id,
                db.func.count(Note.note_id).label('missing_count')
            ).filter(
                missing_condition
            ).group_by(Note.user_id).order_by(db.desc('missing_count')).all()
            
            total = sum(count for _, count in results)
            print(f"【干运行模式】")
            print(f"将处理 {len(results)} 个用户，共 {total} 条笔记{target_desc}")
            per_note_seconds = 3.0 if args.detail else 0.5
            speed_hint = "详情模式，需补齐深度字段，速度较慢" if args.detail else "使用列表页数据，速度较快"
            print(f"预计时间: {total * per_note_seconds / 60:.1f} 分钟 （{speed_hint}）")
        elif args.user_id:
            # 处理单个用户
            from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
            xhs_apis = XHS_Apis()
            cookie_str = get_cookie_str()
            if cookie_str:
                progress = load_progress() if not args.no_resume else {'processed_note_ids': [], 'last_user_id': None, 'stats': {'success': 0, 'failed': 0, 'skipped': 0}}
                fix_notes_for_user(
                    args.user_id, xhs_apis, cookie_str, progress,
                    max_notes=args.max,
                    detail_mode=args.detail,
                    include_upload_time=args.detail
                )
            else:
                print("错误：未找到有效的Cookie")
        else:
            # 处理所有用户
            fix_all_users(
                max_notes_per_user=args.max,
                resume=not args.no_resume,
                detail_mode=args.detail
            )

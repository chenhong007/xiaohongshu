#!/usr/bin/env python3
"""
修复缺失字段的笔记数据

此脚本用于修复数据库中缺失 upload_time、desc 等关键字段的笔记。
这些字段只能通过详情 API 获取，列表 API 不返回。

使用方法:
    python3 fix_missing_fields.py [--user-id USER_ID] [--limit LIMIT] [--dry-run]

参数:
    --user-id: 只修复指定用户的笔记
    --limit: 最多修复多少条笔记 (默认: 100)
    --dry-run: 只统计，不实际修复
"""

import argparse
import json
import os
import sys
import time
import random
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import Note, Account, Cookie
from app.services.sync_service import SyncService

# Spider_XHS imports
try:
    from Spider_XHS.main import Data_Spider
    from Spider_XHS.apis.xhs_pc_apis import XHS_Apis
    from Spider_XHS.xhs_utils.data_util import handle_note_info
    SPIDER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Spider_XHS not available: {e}")
    SPIDER_AVAILABLE = False


def get_notes_with_missing_fields(user_id=None, limit=100):
    """获取缺失关键字段的笔记"""
    query = Note.query
    
    if user_id:
        query = query.filter(Note.user_id == user_id)
    
    # 查找缺失 upload_time 的笔记（这是最关键的指标）
    query = query.filter(
        db.or_(
            Note.upload_time.is_(None),
            Note.upload_time == ''
        )
    )
    
    # 按最后更新时间排序，优先修复最近的
    query = query.order_by(Note.last_updated.desc())
    
    if limit:
        query = query.limit(limit)
    
    return query.all()


def get_notes_statistics():
    """获取笔记数据统计"""
    total = Note.query.count()
    
    # 缺失 upload_time
    missing_upload_time = Note.query.filter(
        db.or_(Note.upload_time.is_(None), Note.upload_time == '')
    ).count()
    
    # 缺失 desc
    missing_desc = Note.query.filter(Note.desc.is_(None)).count()
    
    # 缺失 collected_count
    missing_collected = Note.query.filter(Note.collected_count.is_(None)).count()
    
    # 缺失 comment_count
    missing_comment = Note.query.filter(Note.comment_count.is_(None)).count()
    
    # 缺失 share_count
    missing_share = Note.query.filter(Note.share_count.is_(None)).count()
    
    return {
        'total': total,
        'missing_upload_time': missing_upload_time,
        'missing_desc': missing_desc,
        'missing_collected_count': missing_collected,
        'missing_comment_count': missing_comment,
        'missing_share_count': missing_share,
        'complete': total - missing_upload_time,
        'complete_percent': round((total - missing_upload_time) / total * 100, 1) if total > 0 else 0
    }


def fix_note_detail(note, xhs_apis, data_spider, cookie_str, account_xsec_token=None):
    """修复单个笔记的详情数据"""
    note_id = note.note_id
    
    # 尝试获取笔记级别的 xsec_token
    xsec_token = note.xsec_token or account_xsec_token or ''
    
    if not xsec_token:
        print(f"  ⚠ 笔记 {note_id} 缺少 xsec_token，跳过")
        return False, "missing_xsec_token"
    
    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"
    
    # 尝试获取详情
    for retry in range(3):
        try:
            success, msg, note_info = data_spider.spider_note(note_url, cookie_str)
            
            if '频次异常' in str(msg) or '频繁操作' in str(msg):
                wait_time = random.uniform(30, 60) * (retry + 1)
                print(f"  ⚠ 频率限制，等待 {wait_time:.0f} 秒...")
                time.sleep(wait_time)
                continue
            
            if not success:
                if retry < 2:
                    time.sleep(random.uniform(3, 6))
                    continue
                return False, msg
            
            if not note_info:
                return False, "empty_response"
            
            # 更新笔记数据
            if note_info.get('note_card'):
                card = note_info['note_card']
                
                # 更新 upload_time
                if 'time' in card:
                    from Spider_XHS.xhs_utils.data_util import timestamp_to_str
                    note.upload_time = timestamp_to_str(card['time'])
                
                # 更新 desc
                if 'desc' in card:
                    note.desc = card['desc']
                
                # 更新互动数据
                interact = card.get('interact_info', {})
                if 'liked_count' in interact:
                    note.liked_count = SyncService._parse_count(interact['liked_count'])
                if 'collected_count' in interact:
                    note.collected_count = SyncService._parse_count(interact['collected_count'])
                if 'comment_count' in interact:
                    note.comment_count = SyncService._parse_count(interact['comment_count'])
                if 'share_count' in interact:
                    note.share_count = SyncService._parse_count(interact['share_count'])
                
                # 更新图片列表
                if 'image_list' in card:
                    image_urls = []
                    for img in card['image_list']:
                        try:
                            url = img.get('info_list', [{}])[-1].get('url', '')
                            if url:
                                image_urls.append(url)
                        except:
                            pass
                    if image_urls:
                        note.image_list = json.dumps(image_urls)
                
                # 更新视频地址
                if card.get('type') == 'video' and 'video' in card:
                    video_key = card['video'].get('consumer', {}).get('origin_video_key', '')
                    if video_key:
                        note.video_addr = f'https://sns-video-bd.xhscdn.com/{video_key}'
                
                # 更新 IP 位置
                if 'ip_location' in card:
                    note.ip_location = card['ip_location']
                
                note.last_updated = datetime.utcnow()
                db.session.commit()
                return True, "success"
            
            return False, "invalid_response_format"
            
        except Exception as e:
            if retry < 2:
                time.sleep(random.uniform(3, 6))
                continue
            return False, str(e)
    
    return False, "max_retries_exceeded"


def main():
    parser = argparse.ArgumentParser(description='修复缺失字段的笔记数据')
    parser.add_argument('--user-id', type=str, help='只修复指定用户的笔记')
    parser.add_argument('--limit', type=int, default=100, help='最多修复多少条笔记')
    parser.add_argument('--dry-run', action='store_true', help='只统计，不实际修复')
    parser.add_argument('--stats-only', action='store_true', help='只显示统计信息')
    args = parser.parse_args()
    
    app = create_app()
    
    with app.app_context():
        # 显示统计信息
        print("\n" + "=" * 60)
        print("📊 笔记数据统计")
        print("=" * 60)
        
        stats = get_notes_statistics()
        print(f"总笔记数: {stats['total']}")
        print(f"数据完整: {stats['complete']} ({stats['complete_percent']}%)")
        print(f"\n缺失字段统计:")
        print(f"  - upload_time (发布时间): {stats['missing_upload_time']}")
        print(f"  - desc (内容详情): {stats['missing_desc']}")
        print(f"  - collected_count (收藏数): {stats['missing_collected_count']}")
        print(f"  - comment_count (评论数): {stats['missing_comment_count']}")
        print(f"  - share_count (转发数): {stats['missing_share_count']}")
        
        if args.stats_only:
            return
        
        if args.dry_run:
            print("\n" + "=" * 60)
            print("🔍 Dry Run 模式 - 只统计不修复")
            print("=" * 60)
        
        # 获取需要修复的笔记
        notes = get_notes_with_missing_fields(args.user_id, args.limit)
        print(f"\n找到 {len(notes)} 条需要修复的笔记")
        
        if not notes:
            print("✓ 没有需要修复的笔记")
            return
        
        if args.dry_run:
            print("\n需要修复的笔记:")
            for i, note in enumerate(notes[:20]):
                print(f"  {i+1}. {note.note_id} - {note.title[:30] if note.title else '无标题'}...")
            if len(notes) > 20:
                print(f"  ... 还有 {len(notes) - 20} 条")
            return
        
        # 检查依赖
        if not SPIDER_AVAILABLE:
            print("❌ Spider_XHS 模块不可用，无法修复")
            return
        
        # 获取 Cookie
        cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
        if not cookie:
            print("❌ 没有有效的 Cookie，请先登录")
            return
        
        cookie_str = cookie.get_cookie_str()
        if not cookie_str:
            print("❌ Cookie 为空")
            return
        
        print(f"\n使用 Cookie: {cookie.nickname or cookie.user_id}")
        
        # 初始化 API
        xhs_apis = XHS_Apis()
        data_spider = Data_Spider()
        
        # 开始修复
        print("\n" + "=" * 60)
        print("🔧 开始修复")
        print("=" * 60)
        
        success_count = 0
        fail_count = 0
        skip_count = 0
        
        for i, note in enumerate(notes):
            print(f"\n[{i+1}/{len(notes)}] 修复笔记: {note.note_id}")
            print(f"  标题: {note.title[:40] if note.title else '无标题'}...")
            
            # 获取用户级别的 xsec_token
            account = Account.query.filter_by(user_id=note.user_id).first()
            account_xsec_token = None
            if account:
                # 尝试动态获取
                account_xsec_token = SyncService._fetch_user_xsec_token(
                    note.user_id, xhs_apis, cookie_str
                )
            
            success, result = fix_note_detail(
                note, xhs_apis, data_spider, cookie_str, account_xsec_token
            )
            
            if success:
                print(f"  ✓ 修复成功")
                print(f"    upload_time: {note.upload_time}")
                print(f"    liked: {note.liked_count}, collected: {note.collected_count}, comment: {note.comment_count}")
                success_count += 1
            elif result == "missing_xsec_token":
                print(f"  ⚠ 跳过 (缺少 xsec_token)")
                skip_count += 1
            else:
                print(f"  ✗ 修复失败: {result}")
                fail_count += 1
            
            # 随机延迟，避免频率限制
            delay = random.uniform(3, 8)
            print(f"  等待 {delay:.1f} 秒...")
            time.sleep(delay)
        
        # 显示结果
        print("\n" + "=" * 60)
        print("📋 修复完成")
        print("=" * 60)
        print(f"成功: {success_count}")
        print(f"失败: {fail_count}")
        print(f"跳过: {skip_count}")
        
        # 显示最新统计
        print("\n最新统计:")
        stats = get_notes_statistics()
        print(f"数据完整: {stats['complete']} / {stats['total']} ({stats['complete_percent']}%)")


if __name__ == '__main__':
    main()


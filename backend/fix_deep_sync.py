#!/usr/bin/env python3
"""
深度同步修复脚本

功能：
1. 检查数据库中所有缺失深度字段（upload_time, collected_count 等）的笔记
2. 以更慢的速度（5-15秒间隔）重新获取详情，避免被限流
3. 支持断点续传，可随时中断后继续
4. 诊断限流状态

使用方法：
    # 在 Docker 容器内运行
    docker exec -it xhs-backend python fix_deep_sync.py --check        # 仅检查缺失数据
    docker exec -it xhs-backend python fix_deep_sync.py --diagnose     # 诊断限流状态
    docker exec -it xhs-backend python fix_deep_sync.py --fix          # 修复缺失数据
    docker exec -it xhs-backend python fix_deep_sync.py --fix --user-id 59757acd50c4b45e6e9a90df  # 只修复指定用户
    docker exec -it xhs-backend python fix_deep_sync.py --fix --limit 50   # 限制修复数量
    
⚠️ 注意：如果被限流，需要等待几小时甚至更长时间才能恢复！
   建议：更换 Cookie（重新登录）或等待限流解除后再尝试
"""

import os
import sys
import time
import json
import random
import argparse
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.extensions import db
from app.models import Note, Account, Cookie
from app.config import Config

# 全局配置
MIN_DELAY = 5.0       # 最小延迟（秒）
MAX_DELAY = 15.0      # 最大延迟（秒）
EXTRA_PAUSE_CHANCE = 0.2   # 额外长暂停概率
EXTRA_PAUSE_MAX = 30.0     # 额外长暂停最大秒数
MAX_RETRIES = 5       # 最大重试次数
RETRY_DELAY_BASE = 10 # 重试基础延迟


def get_missing_notes_query(user_id=None):
    """构建缺失深度数据的笔记查询"""
    # 缺失的条件：upload_time 为空 或 collected_count/comment_count/share_count 都为0
    missing_condition = db.or_(
        Note.upload_time.is_(None),
        Note.upload_time == '',
        db.and_(
            Note.collected_count == 0,
            Note.comment_count == 0,
            Note.share_count == 0
        )
    )
    
    query = Note.query.filter(missing_condition)
    
    if user_id:
        query = query.filter(Note.user_id == user_id)
    
    return query


def check_missing_data(user_id=None):
    """检查缺失深度数据的笔记"""
    print("\n" + "=" * 60)
    print("📊 数据完整性检查报告")
    print("=" * 60)
    
    # 总笔记数
    total_notes = Note.query.count()
    print(f"\n📝 总笔记数: {total_notes}")
    
    # 缺失 upload_time
    missing_upload_time = Note.query.filter(
        db.or_(Note.upload_time.is_(None), Note.upload_time == '')
    ).count()
    print(f"⚠️  缺失发布时间 (upload_time): {missing_upload_time}")
    
    # 缺失互动数据（三项都为0）
    missing_interaction = Note.query.filter(
        Note.collected_count == 0,
        Note.comment_count == 0,
        Note.share_count == 0
    ).count()
    print(f"⚠️  缺失互动数据 (collected/comment/share 都为0): {missing_interaction}")
    
    # 缺失视频地址（视频类型）
    missing_video = Note.query.filter(
        Note.type == '视频',
        db.or_(Note.video_addr.is_(None), Note.video_addr == '')
    ).count()
    print(f"⚠️  视频笔记缺失视频地址: {missing_video}")
    
    # 缺失本地封面
    missing_cover = Note.query.filter(
        db.or_(Note.cover_local.is_(None), Note.cover_local == '')
    ).count()
    print(f"⚠️  缺失本地封面: {missing_cover}")
    
    # 综合：需要深度同步的笔记
    need_fix = get_missing_notes_query(user_id).count()
    print(f"\n🔧 需要修复的笔记总数: {need_fix}")
    
    # 按用户统计
    print("\n📊 按用户统计缺失数据:")
    print("-" * 50)
    
    user_stats = db.session.query(
        Note.user_id,
        Note.nickname,
        db.func.count(Note.note_id).label('missing_count')
    ).filter(
        db.or_(Note.upload_time.is_(None), Note.upload_time == '')
    ).group_by(Note.user_id).order_by(db.desc('missing_count')).all()
    
    for i, (uid, nickname, count) in enumerate(user_stats[:20], 1):
        print(f"  {i:2d}. {nickname or uid[:16]}: {count} 条")
    
    if len(user_stats) > 20:
        print(f"  ... 还有 {len(user_stats) - 20} 个用户")
    
    print("\n" + "=" * 60)
    return need_fix


def get_cookie_str():
    """获取有效的 Cookie 字符串"""
    cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if cookie:
        return cookie.get_cookie_str()
    return None


def diagnose_rate_limit():
    """诊断当前的限流状态"""
    print("\n" + "=" * 60)
    print("🔍 限流状态诊断")
    print("=" * 60)
    
    # 检查 Cookie
    cookie_str = get_cookie_str()
    if not cookie_str:
        print("❌ 未找到有效的 Cookie，请先登录")
        return
    print("✅ Cookie 状态正常")
    
    # 检查 Cookie 详情
    cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
    if cookie:
        print(f"   用户: {cookie.nickname}")
        print(f"   最后检查: {cookie.last_checked}")
    
    # 初始化 API
    try:
        from apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        print("✅ API 初始化成功")
    except Exception as e:
        print(f"❌ API 初始化失败: {e}")
        return
    
    # 尝试获取一个有详情的笔记（已知成功的）
    test_note_id = "693804f3000000000d03c410"  # 已知有详情的笔记
    test_url = f"https://www.xiaohongshu.com/explore/{test_note_id}"
    
    print(f"\n🧪 测试请求（笔记 ID: {test_note_id}）...")
    
    success, msg, result = xhs_apis.get_note_info(test_url, cookie_str)
    
    if '频次异常' in str(msg) or '频繁操作' in str(msg):
        print(f"❌ 当前处于限流状态: {msg}")
        print("\n💡 建议:")
        print("   1. 等待 2-6 小时后再试")
        print("   2. 更换 Cookie（重新登录另一个账号）")
        print("   3. 如果使用代理，尝试更换 IP")
    elif not success:
        print(f"⚠️  请求失败: {msg}")
        if '登录' in str(msg) or 'unauthorized' in str(msg).lower():
            print("   可能是 Cookie 已过期，请重新登录")
    else:
        print("✅ 请求成功，当前未被限流！")
        if result and result.get('data', {}).get('items'):
            print("   可以正常获取详情数据")
    
    # 检查账号的 xsec_token
    print("\n📊 账号 xsec_token 状态:")
    accounts = Account.query.all()
    with_token = sum(1 for a in accounts if a.xsec_token)
    print(f"   有 token: {with_token}/{len(accounts)} 个账号")
    
    print("\n" + "=" * 60)


def sleep_with_jitter():
    """带随机抖动的延迟"""
    delay = random.uniform(MIN_DELAY, MAX_DELAY)
    
    # 偶尔增加额外长暂停
    if random.random() < EXTRA_PAUSE_CHANCE:
        extra = random.uniform(5.0, EXTRA_PAUSE_MAX)
        delay += extra
        print(f"  💤 额外暂停 {extra:.1f}s...")
    
    time.sleep(delay)


def fix_note_detail(note, xhs_apis, cookie_str, account_xsec_token):
    """修复单个笔记的详情数据"""
    from xhs_utils.data_util import handle_note_info
    
    note_id = note.note_id
    
    # 构建笔记URL
    xsec_token = note.xsec_token or account_xsec_token
    if xsec_token:
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search"
    else:
        note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
    
    # 带重试的详情获取
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            wait_time = RETRY_DELAY_BASE * (attempt + 1) + random.uniform(5, 15)
            print(f"    ⏳ 重试 {attempt + 1}/{MAX_RETRIES}，等待 {wait_time:.1f}s...")
            time.sleep(wait_time)
        
        success, msg, note_detail = xhs_apis.get_note_info(note_url, cookie_str)
        
        # 检查限流
        if '频次异常' in str(msg) or '频繁操作' in str(msg):
            print(f"    ⚠️  被限流: {msg}")
            if attempt < MAX_RETRIES - 1:
                continue
            else:
                print(f"    ❌ 达到最大重试次数，跳过")
                return False
        
        # 检查笔记不可用
        if '暂时无法浏览' in str(msg) or '笔记不存在' in str(msg):
            print(f"    ⚠️  笔记不可用: {msg}")
            return False
        
        if not success:
            print(f"    ⚠️  获取失败: {msg}")
            if attempt < MAX_RETRIES - 1:
                continue
            return False
        
        if success and note_detail:
            try:
                data = note_detail.get('data')
                if data and data.get('items') and len(data['items']) > 0:
                    note_data = data['items'][0]
                    note_data['url'] = note_url
                    cleaned_data = handle_note_info(note_data, from_list=False, xsec_token=xsec_token)
                    
                    # 更新笔记数据
                    if cleaned_data['upload_time']:
                        note.upload_time = cleaned_data['upload_time']
                    if cleaned_data['collected_count'] is not None:
                        note.collected_count = cleaned_data['collected_count']
                    if cleaned_data['comment_count'] is not None:
                        note.comment_count = cleaned_data['comment_count']
                    if cleaned_data['share_count'] is not None:
                        note.share_count = cleaned_data['share_count']
                    if cleaned_data['video_addr']:
                        note.video_addr = cleaned_data['video_addr']
                    if cleaned_data['desc']:
                        note.desc = cleaned_data['desc']
                    if cleaned_data['image_list']:
                        new_count = len(cleaned_data['image_list'])
                        try:
                            old_list = json.loads(note.image_list) if note.image_list else []
                            old_count = len(old_list)
                        except:
                            old_count = 0
                        if new_count > old_count:
                            note.image_list = json.dumps(cleaned_data['image_list'])
                    if cleaned_data['tags']:
                        note.tags = json.dumps(cleaned_data['tags'])
                    if cleaned_data['ip_location']:
                        note.ip_location = cleaned_data['ip_location']
                    
                    note.last_updated = datetime.utcnow()
                    db.session.commit()
                    
                    return True
                else:
                    print(f"    ⚠️  响应数据为空")
                    if attempt < MAX_RETRIES - 1:
                        continue
                    return False
            except Exception as e:
                print(f"    ❌ 解析错误: {e}")
                return False
    
    return False


def fix_missing_data(user_id=None, limit=None, dry_run=False):
    """修复缺失的深度数据"""
    print("\n" + "=" * 60)
    print("🔧 开始修复缺失的深度数据")
    print("=" * 60)
    
    if dry_run:
        print("⚠️  DRY RUN 模式，不会实际修改数据")
    
    # 获取 Cookie
    cookie_str = get_cookie_str()
    if not cookie_str:
        print("❌ 未找到有效的 Cookie，请先登录")
        return
    
    print("✅ Cookie 有效")
    
    # 初始化 API
    try:
        from apis.xhs_pc_apis import XHS_Apis
        xhs_apis = XHS_Apis()
        print("✅ API 初始化成功")
    except Exception as e:
        print(f"❌ API 初始化失败: {e}")
        return
    
    # 获取需要修复的笔记
    query = get_missing_notes_query(user_id)
    if limit:
        query = query.limit(limit)
    
    notes = query.all()
    total = len(notes)
    
    if total == 0:
        print("✅ 没有需要修复的笔记")
        return
    
    print(f"\n📝 待修复笔记: {total} 条")
    print(f"⏱️  预计耗时: {total * (MIN_DELAY + MAX_DELAY) / 2 / 60:.1f} - {total * MAX_DELAY / 60:.1f} 分钟")
    print(f"⚙️  延迟配置: {MIN_DELAY}-{MAX_DELAY}秒，额外暂停概率 {EXTRA_PAUSE_CHANCE*100}%")
    
    if not dry_run:
        print("\n按 Ctrl+C 可随时中断（进度已保存）")
        time.sleep(3)
    
    # 获取账号的 xsec_token 映射
    account_tokens = {}
    accounts = Account.query.all()
    for acc in accounts:
        if acc.xsec_token:
            account_tokens[acc.user_id] = acc.xsec_token
    
    # 开始修复
    success_count = 0
    fail_count = 0
    skip_count = 0
    
    print("\n" + "-" * 60)
    
    try:
        for i, note in enumerate(notes, 1):
            note_id = note.note_id
            title = (note.title or '')[:30]
            nickname = note.nickname or note.user_id[:10]
            
            print(f"\n[{i}/{total}] {nickname} - {title}...")
            
            if dry_run:
                print(f"  📋 DRY RUN: 将修复 note_id={note_id}")
                skip_count += 1
                continue
            
            # 获取账号的 xsec_token
            account_xsec_token = account_tokens.get(note.user_id, '')
            
            # 修复笔记详情
            if fix_note_detail(note, xhs_apis, cookie_str, account_xsec_token):
                success_count += 1
                print(f"  ✅ 成功！upload_time={note.upload_time}")
            else:
                fail_count += 1
                print(f"  ❌ 失败")
            
            # 延迟
            if i < total:
                print(f"  💤 等待中...")
                sleep_with_jitter()
    
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断，保存当前进度...")
        db.session.commit()
    
    # 打印结果
    print("\n" + "=" * 60)
    print("📊 修复结果")
    print("=" * 60)
    print(f"  ✅ 成功: {success_count}")
    print(f"  ❌ 失败: {fail_count}")
    if dry_run:
        print(f"  📋 跳过 (dry run): {skip_count}")
    print("=" * 60)


def main():
    global MIN_DELAY, MAX_DELAY
    
    parser = argparse.ArgumentParser(description='深度同步修复脚本')
    parser.add_argument('--check', action='store_true', help='仅检查缺失数据')
    parser.add_argument('--diagnose', action='store_true', help='诊断限流状态')
    parser.add_argument('--fix', action='store_true', help='修复缺失数据')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行，不实际修改')
    parser.add_argument('--user-id', type=str, help='只处理指定用户ID')
    parser.add_argument('--limit', type=int, help='限制处理数量')
    parser.add_argument('--min-delay', type=float, default=MIN_DELAY, help=f'最小延迟秒数 (默认 {MIN_DELAY})')
    parser.add_argument('--max-delay', type=float, default=MAX_DELAY, help=f'最大延迟秒数 (默认 {MAX_DELAY})')
    
    args = parser.parse_args()
    
    # 更新延迟配置
    MIN_DELAY = args.min_delay
    MAX_DELAY = args.max_delay
    
    # 创建 Flask 应用上下文
    app = create_app()
    
    with app.app_context():
        if args.diagnose:
            diagnose_rate_limit()
        elif args.check:
            check_missing_data(args.user_id)
        elif args.fix:
            fix_missing_data(args.user_id, args.limit, args.dry_run)
        else:
            # 默认先检查
            need_fix = check_missing_data(args.user_id)
            if need_fix > 0:
                print("\n💡 提示:")
                print("   1. 使用 --diagnose 诊断限流状态")
                print("   2. 使用 --fix 参数开始修复")
                print("   例如: python fix_deep_sync.py --diagnose")
                print("   例如: python fix_deep_sync.py --fix --limit 50")


if __name__ == '__main__':
    main()


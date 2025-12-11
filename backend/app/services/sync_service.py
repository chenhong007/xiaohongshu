"""
同步服务 - 处理笔记数据同步
"""
import json
import os
import time
import random
import threading
from datetime import datetime
from urllib.parse import urlparse
from flask import current_app
import requests

from ..extensions import db
from ..models import Account, Note, Cookie
from ..utils.logger import get_logger, log_sync_event
from ..config import Config
from xhs_utils.xhs_util import get_common_headers

# 获取日志器
logger = get_logger('sync')


class SyncService:
    """同步服务类"""
    
    _stop_event = threading.Event()
    
    @staticmethod
    def _mark_accounts_failed(account_ids, message):
        """将指定账号标记为失败，避免前端一直显示'准备中'"""
        if not account_ids:
            return
        try:
            Account.query.filter(Account.id.in_(list(account_ids))).update(
                {
                    'status': 'failed',
                    'error_message': message,
                    'progress': 0
                },
                synchronize_session=False
            )
            db.session.commit()
        except Exception as e:
            logger.error(f"批量标记账号失败: {e}")
            db.session.rollback()
    
    @staticmethod
    def stop_sync():
        """停止同步任务"""
        logger.info("正在停止同步任务...")
        SyncService._stop_event.set()

    @staticmethod
    def _is_media_missing(note):
        """检查笔记的媒体资源是否缺失"""
        if not note:
            return True
            
        try:
            # 1. 检查封面
            if not note.cover_local:
                return True
            cover_path = os.path.join(Config.MEDIA_PATH, os.path.basename(note.cover_local))
            if not os.path.exists(cover_path) or os.path.getsize(cover_path) < 1024:
                return True
                
            # 2. 检查图集/视频目录
            note_dir = os.path.join(Config.MEDIA_PATH, str(note.note_id))
            if not os.path.exists(note_dir):
                # 如果没有目录，肯定缺失
                return True
                
            # 如果是图集，检查是否有图片
            if note.type in ['图集', 'normal']:
                try:
                    img_list = json.loads(note.image_list) if note.image_list else []
                    if len(img_list) > 0:
                        # 简单检查：目录下文件数量是否匹配（或至少有文件）
                        # 严格检查太耗时，这里只要目录下有jpg文件就算有
                        files = [f for f in os.listdir(note_dir) if f.endswith('.jpg') and os.path.getsize(os.path.join(note_dir, f)) > 1024]
                        if len(files) == 0:
                            return True
                except:
                    pass
            
            # 如果是视频，检查是否有视频文件
            if note.type == '视频':
                video_path = os.path.join(note_dir, 'video.mp4')
                if not os.path.exists(video_path) or os.path.getsize(video_path) < 1024:
                    return True
                    
        except Exception as e:
            logger.warning(f"Error checking media for note {note.note_id}: {e}")
            return True
            
        return False

    @staticmethod
    def _handle_auth_error(msg):
        """检查错误信息是否为认证错误,如果是则标记Cookie失效"""
        auth_errors = ['未登录', '登录已过期', '需要登录', '401', '403', 'Unauthorized']
        if any(error in str(msg) for error in auth_errors):
            logger.warning(f"检测到认证错误: {msg},正在标记Cookie失效...")
            try:
                # 重新查询当前激活的 cookie
                cookie = Cookie.query.filter_by(is_active=True).first()
                if cookie:
                    cookie.stop_run_timer()
                    cookie.is_valid = False
                    cookie.last_checked = datetime.utcnow()
                    db.session.commit()
                    logger.info("Cookie 已标记为失效")
                return True
            except Exception as e:
                logger.error(f"标记Cookie失效时出错: {e}")
        return False

    @staticmethod
    def _sleep_with_jitter(sync_mode):
        """深度同步时增加随机间隔，降低爬虫特征"""
        if sync_mode != 'deep':
            return

        cfg = current_app.config if current_app else {}
        try:
            min_delay = float(cfg.get('DEEP_SYNC_DELAY_MIN', 0.8))
            max_delay = float(cfg.get('DEEP_SYNC_DELAY_MAX', 1.8))
            extra_prob = float(cfg.get('DEEP_SYNC_EXTRA_PAUSE_CHANCE', 0.12))
            extra_max = float(cfg.get('DEEP_SYNC_EXTRA_PAUSE_MAX', 3.0))
        except Exception:
            min_delay, max_delay, extra_prob, extra_max = 0.8, 1.8, 0.12, 3.0

        min_delay = max(0.1, min_delay)
        max_delay = max(min_delay, max_delay)

        delay = random.uniform(min_delay, max_delay)
        if random.random() < extra_prob:
            delay += random.uniform(0.5, extra_max)

        time.sleep(delay)

    @staticmethod
    def get_cookie_str():
        """获取有效的Cookie字符串（已解密）"""
        cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
        if cookie:
            # 使用新的解密方法
            return cookie.get_cookie_str()
        
        # 从配置获取
        from ..config import Config
        return getattr(Config, 'XHS_COOKIES', '')
    
    @staticmethod
    def start_sync(account_ids, sync_mode='fast'):
        """启动后台同步任务"""
        from .. import create_app
        app = create_app()
        
        # 重置停止标志
        SyncService._stop_event.clear()
        
        thread = threading.Thread(target=SyncService._run_sync, args=(app, account_ids, sync_mode))
        thread.daemon = True
        thread.start()
        
        logger.info(f"同步任务已启动: {len(account_ids)} 个账号, 模式: {sync_mode}")
    
    @staticmethod
    def _run_sync(app, account_ids, sync_mode):
        """在后台线程中执行同步"""
        with app.app_context():
            SyncService._sync_accounts(account_ids, sync_mode)
    
    @staticmethod
    def _sync_accounts(account_ids, sync_mode):
        """同步账号的笔记数据"""
        logger.info(f"开始同步账号: {account_ids}, 模式: {sync_mode}")
        
        remaining_ids = set(account_ids)
        cookie_str = SyncService.get_cookie_str()
        if not cookie_str:
            logger.error("未找到有效的 Cookie")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': '未找到有效的Cookie,请先登录小红书'},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        try:
            from apis.xhs_pc_apis import XHS_Apis
            from xhs_utils.data_util import handle_note_info
            xhs_apis = XHS_Apis()
        except Exception as e:
            error_msg = f"初始化API失败: {e}"
            logger.error(f"初始化XHS APIs失败: {e}")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': error_msg},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        for acc_id in account_ids:
            # 检查是否停止
            if SyncService._stop_event.is_set():
                logger.info("同步已被用户停止")
                break
                
            try:
                account = Account.query.get(acc_id)
                if not account:
                    continue
                
                # 当前账号即将处理，移出剩余集合
                remaining_ids.discard(acc_id)
                auth_error_msg = None
                
                # 更新状态为处理中,清除之前的错误信息
                account.status = 'processing'
                account.progress = 0
                # 在开始同步时立即重置已采集数，避免前端轮询时显示旧数据
                account.loaded_msgs = 0
                account.error_message = None
                db.session.commit()
                
                # 构建用户URL,包含xsec_token用于API验证
                xsec_token = account.xsec_token or ''
                warning_msg = None
                
                # 如果没有xsec_token,尝试获取
                if not xsec_token:
                    logger.info(f"No xsec_token for account {account.user_id}, attempting to fetch...")
                    try:
                        success_token, msg_token, fetched_token = xhs_apis.get_user_xsec_token(account.user_id, cookie_str)
                        if success_token and fetched_token:
                            xsec_token = fetched_token
                            # 保存到数据库以便后续使用
                            account.xsec_token = xsec_token
                            db.session.commit()
                            logger.info(f"Successfully fetched xsec_token for {account.user_id}")
                        else:
                            logger.info(f"Could not fetch xsec_token: {msg_token}")
                    except Exception as e:
                        logger.info(f"Error fetching xsec_token: {e}")
                
                if xsec_token:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                else:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}'
                    warning_msg = f"缺少xsec_token,可能导致同步失败"
                    logger.info(f"Warning: No xsec_token for account {account.user_id}, sync may fail")
                
                # 获取用户所有笔记列表
                success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookie_str)
                
                # 策略优化:如果获取成功但列表为空,尝试强制刷新xsec_token并重试一次
                # 这解决了一些因token过期或无效导致看似成功但无数据的问题
                if success and not all_note_info:
                    logger.info(f"Got 0 notes for {account.user_id}, attempting to refresh xsec_token and retry...")
                    try:
                        # 强制重新获取 token
                        success_token, msg_token, fetched_token = xhs_apis.get_user_xsec_token(account.user_id, cookie_str)
                        
                        if success_token and fetched_token:
                            # 即使token一样也可能是服务端状态问题,但通常不一样
                            if fetched_token != xsec_token:
                                logger.info(f"Refreshed xsec_token: {fetched_token[:10]}...")
                                xsec_token = fetched_token
                                account.xsec_token = xsec_token
                                db.session.commit()
                                
                                # 使用新token重试
                                user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                                success_retry, msg_retry, all_note_info_retry = xhs_apis.get_user_all_notes(user_url, cookie_str)
                                
                                if success_retry and all_note_info_retry:
                                    logger.info(f"Retry success! Got {len(all_note_info_retry)} notes.")
                                    success = success_retry
                                    msg = msg_retry
                                    all_note_info = all_note_info_retry
                                else:
                                    logger.info(f"Retry result: success={success_retry}, count={len(all_note_info_retry) if all_note_info_retry else 0}")
                            else:
                                print("Fetched token is identical to current token, skipping retry.")
                        else:
                            logger.info(f"Failed to refresh token: {msg_token}")
                    except Exception as e:
                        logger.info(f"Error during token refresh retry: {e}")

                if not success:
                    # 检查是否为认证错误
                    if SyncService._handle_auth_error(msg):
                        error_msg = f"Cookie已失效,请重新登录。原始错误: {msg}"
                        auth_error_msg = error_msg
                        # 标记停止,不再尝试后续账号
                        SyncService.stop_sync()
                        SyncService._mark_accounts_failed(remaining_ids, error_msg)
                    else:
                        error_msg = f"获取笔记列表失败: {msg}"

                    if warning_msg:
                        error_msg = f"{warning_msg}。{error_msg}"
                    logger.info(f"Failed to get notes for {account.user_id}: {msg}")
                    account.status = 'failed'
                    account.error_message = error_msg
                    db.session.commit()
                    if auth_error_msg:
                        break
                    continue
                
                # 【关键修复】如果API成功但返回空列表,标记为失败而不是继续
                if success and not all_note_info:
                    error_msg = "获取笔记列表为空,可能是xsec_token失效或该用户没有公开笔记"
                    if warning_msg:
                        error_msg = f"{warning_msg}。{error_msg}"
                    logger.info(f"Empty notes for {account.user_id} after all retries")
                    account.status = 'failed'
                    account.error_message = error_msg
                    account.total_msgs = 0
                    account.loaded_msgs = 0
                    account.progress = 0
                    db.session.commit()
                    continue

                # 尝试获取并更新用户信息（头像、昵称、粉丝数等）
                try:
                    success_info, msg_info, user_info_res = xhs_apis.get_user_info(account.user_id, cookie_str)
                    
                    if not success_info and SyncService._handle_auth_error(msg_info):
                        auth_error_msg = f"Cookie已失效,同步终止。错误: {msg_info}"
                        SyncService.stop_sync()
                        SyncService._mark_accounts_failed(remaining_ids, auth_error_msg)
                    
                    if success_info and user_info_res and user_info_res.get('data'):
                        user_data = user_info_res['data']
                        if user_data:
                            account.name = user_data.get('basic_info', {}).get('nickname') or account.name
                            account.avatar = user_data.get('basic_info', {}).get('images') or account.avatar
                            account.desc = user_data.get('basic_info', {}).get('desc') or account.desc
                            
                            # 更新互动数据
                            interactions = user_data.get('interactions', [])
                            for interaction in interactions:
                                if interaction.get('type') == 'fans':
                                    account.fans = interaction.get('count')
                                elif interaction.get('type') == 'follows':
                                    account.follows = interaction.get('count')
                                elif interaction.get('type') == 'interaction':
                                    account.interaction = interaction.get('count')
                            
                            db.session.commit()
                            logger.info(f"Updated user info for {account.user_id}: fans={account.fans}")
                except Exception as e:
                    logger.info(f"Failed to update user info for {account.user_id}: {e}")
                
                total = len(all_note_info)
                account.total_msgs = total
                # 不再重置loaded_msgs为0,而是保留之前的值,或者根据实际情况更新
                # 如果是全新的同步开始,可能需要重置,但如果是增量或者状态更新,这会让人困惑
                # 现在的逻辑是:每次同步都是从头遍历所有笔记,所以重置为0是合理的
                # 但如果total > 0且最终success,loaded_msgs应该等于total
                account.loaded_msgs = 0 
                db.session.commit()
                
                # 处理每个笔记
                # 使用账号的xsec_token作为后备,如果笔记自带xsec_token则优先使用
                account_xsec_token = account.xsec_token or ''
                for idx, simple_note in enumerate(all_note_info):
                    # 检查是否停止
                    if SyncService._stop_event.is_set():
                        print("Sync stopped by user during note processing")
                        break

                    # 【关键修复】兼容API返回的两种字段名:'note_id'和'id'
                    note_id = simple_note.get('note_id') or simple_note.get('id')
                    # 优先使用笔记自带的xsec_token（由get_user_all_notes添加）,否则使用账号的
                    note_xsec_token = simple_note.get('xsec_token') or account_xsec_token
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note_xsec_token}"
                    
                    need_fetch_detail = False
                    
                    if sync_mode == 'deep':
                        # 方案B:深度同步(增量模式)
                        # 检查数据库中是否存在该笔记
                        existing_note = Note.query.filter_by(note_id=note_id).first()
                        
                        if not existing_note:
                            need_fetch_detail = True
                            logger.info(f"Note {note_id} not exists, will fetch detail")
                        else:
                            # 检查关键媒体字段是否缺失(可能是之前极速同步的)
                            if existing_note.type == '视频' and not existing_note.video_addr:
                                need_fetch_detail = True
                                logger.info(f"Note {note_id} is video but missing video_addr, will fetch detail")
                            elif (existing_note.type == '图集' or existing_note.type == 'normal'):
                                # 【关键修复】图集类型需要检查是否只有1张图片（封面）
                                # 列表页API只返回封面，完整图片列表需要从详情页获取
                                try:
                                    img_list = json.loads(existing_note.image_list) if existing_note.image_list else []
                                except:
                                    img_list = []
                                # 如果图片列表为空或只有1张（封面），需要重新获取详情
                                if len(img_list) <= 1:
                                    need_fetch_detail = True
                                    logger.info(f"Note {note_id} is image set but only has {len(img_list)} images, will fetch detail")
                            # 【关键修复】检查是否缺少详情页数据
                            # upload_time是详情页才返回的字段,如果为空说明从未获取过详情
                            # 这时收藏、评论、转发数据也是不准确的(默认为0)
                            if not need_fetch_detail and (not existing_note.upload_time or existing_note.upload_time == ''):
                                need_fetch_detail = True
                                logger.info(f"Note {note_id} missing upload_time, will fetch detail")
                            
                            # 【关键修复】检查是否缺少封面数据（cover_remote 和 cover_local）
                            # 这两个字段是数据库新增的，旧数据可能缺失
                            if not need_fetch_detail and (not existing_note.cover_remote or existing_note.cover_remote == ''):
                                need_fetch_detail = True
                                logger.info(f"Note {note_id} missing cover_remote, will fetch detail")
                            
                            # 【新增】强制检查本地媒体资源是否存在
                            if not need_fetch_detail and SyncService._is_media_missing(existing_note):
                                need_fetch_detail = True
                                logger.info(f"Note {note_id} missing local media files, forcing detail fetch")
                    else:
                        # 方案A:极速同步
                        # 永远只使用列表页数据,不获取详情
                        need_fetch_detail = False

                    if not need_fetch_detail:
                        # 极速更新(只更新互动数据)
                        # 【重要说明】列表页API只返回点赞数,不返回收藏、评论、转发数和发布时间
                        try:
                            # 从列表页数据中提取互动信息
                            cleaned_data = handle_note_info(simple_note, from_list=True)
                            
                            if sync_mode == 'deep':
                                # 深度模式下,如果是旧笔记,只更新点赞数（列表页唯一可用的互动数据）
                                existing_note = Note.query.filter_by(note_id=note_id).first()
                                if existing_note:
                                    # 只更新点赞数,其他数据保留（因为列表页不提供）
                                    if cleaned_data['liked_count'] is not None:
                                        existing_note.liked_count = cleaned_data['liked_count']
                                    existing_note.last_updated = datetime.utcnow()
                                    db.session.commit()
                            else:
                                # 极速模式下,保存/更新笔记
                                # _save_note会智能处理None值（不覆盖已有数据）
                                SyncService._save_note(cleaned_data)
                                
                        except Exception as e:
                            logger.info(f"Error quick updating note {note_id}: {e}")
                    else:
                        # 需要获取详情(深度模式下的新笔记或缺失素材笔记)
                        success, msg, note_detail = xhs_apis.get_note_info(note_url, cookie_str)
                        
                        detail_saved = False
                        
                        if not success:
                            # 检查认证错误
                            if SyncService._handle_auth_error(msg):
                                logger.info(f"Auth error during note detail fetch: {msg}")
                                auth_error_msg = f"Cookie已失效,同步终止。错误: {msg}"
                                SyncService.stop_sync()
                                account.status = 'failed'
                                account.error_message = auth_error_msg
                                db.session.commit()
                                SyncService._mark_accounts_failed(remaining_ids, auth_error_msg)
                                break
                            else:
                                # 非认证错误，记录日志
                                logger.warning(f"Failed to get note detail for {note_id}: {msg}")

                        if success and note_detail:
                            try:
                                # 安全访问嵌套数据,防止NoneType错误
                                data = note_detail.get('data')
                                if data and data.get('items') and len(data['items']) > 0:
                                    note_data = data['items'][0]
                                    note_data['url'] = note_url
                                    cleaned_data = handle_note_info(note_data, from_list=False)
                                    # 深度同步获取详情后，下载所有媒体资源
                                    SyncService._save_note(cleaned_data, download_media=True)
                                    detail_saved = True
                                else:
                                    logger.warning(f"Note {note_id} has no valid data in response")
                            except Exception as e:
                                logger.warning(f"Error parsing note {note_id}: {e}")
                        
                        # 【关键修复】如果详情获取失败，至少保存列表页的基本数据
                        # 这样封面等信息能从列表页获取，不会完全为空
                        if not detail_saved:
                            try:
                                logger.info(f"Saving note {note_id} with list data as fallback")
                                cleaned_data = handle_note_info(simple_note, from_list=True)
                                # 列表页数据，不下载完整媒体（因为没有详情），但封面可以获取
                                SyncService._save_note(cleaned_data, download_media=False)
                            except Exception as e:
                                logger.warning(f"Error saving note {note_id} with list data: {e}")
                        
                        # 请求间隔,避免被封（仅在请求详情页时等待,加入随机抖动）
                        SyncService._sleep_with_jitter(sync_mode)
                    
                    # 更新进度
                    # 只有在确实处理了笔记时才更新loaded_msgs?
                    # 不,我们遍历了列表,所以应该算作已处理（即使是跳过详情获取）
                    # 但为了界面显示准确,如果total为0,progress设为100
                    account.loaded_msgs = idx + 1
                    account.progress = int(((idx + 1) / total) * 100) if total > 0 else 100
                    db.session.commit()
                    
                    # 极速模式下不需要sleep
                    if sync_mode == 'fast':
                        # time.sleep(0.05) 
                        pass
                
                # 完成同步
                if auth_error_msg:
                    # 认证错误时当前账号已标记失败，其余账号也已处理
                    break
                if not SyncService._stop_event.is_set():
                    account.status = 'completed'
                    # 确保进度为100%
                    account.progress = 100
                    # 确保loaded_msgs等于total,即使中途有跳过的情况（只要不是报错退出）
                    # 因为我们遍历了所有笔记列表
                    account.loaded_msgs = total
                    account.last_sync = datetime.utcnow()
                else:
                    # 如果是因为停止而退出循环,且状态仍为processing
                    if account.status == 'processing':
                        account.status = 'failed'
                        account.error_message = account.error_message or "用户手动停止同步"
                
                db.session.commit()
                
            except Exception as e:
                logger.info(f"Error syncing account {acc_id}: {e}")
                # 先回滚session,避免PendingRollbackError
                db.session.rollback()
                try:
                    account = Account.query.get(acc_id)
                    if account:
                        account.status = 'failed'
                        account.error_message = f"同步出错: {str(e)}"
                        db.session.commit()
                except Exception as inner_e:
                    logger.info(f"Error updating account status: {inner_e}")
                    db.session.rollback()
    
    @staticmethod
    def _download_all_media(note_id, note_data):
        """下载笔记的所有媒体资源（图片/视频）到本地归档"""
        try:
            logger.info(f"Starting media download for note {note_id}...")
            # 创建笔记专属目录
            note_dir = os.path.join(Config.MEDIA_PATH, str(note_id))
            if not os.path.exists(note_dir):
                os.makedirs(note_dir)
            
            headers = get_common_headers()
            downloaded_count = 0
            
            # 1. 下载图片列表
            if note_data.get('image_list'):
                logger.info(f"Downloading {len(note_data['image_list'])} images for note {note_id}")
                for idx, img_url in enumerate(note_data['image_list']):
                    # 处理URL，尝试获取无水印版本（如果之前没有处理过）
                    # 这里假设传入的URL已经是最佳URL
                    
                    ext = '.jpg'
                    filename = f"image_{idx}{ext}"
                    filepath = os.path.join(note_dir, filename)
                    
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                        logger.info(f"Skipping existing image {idx} for note {note_id}")
                        continue
                        
                    try:
                        logger.info(f"Downloading image {idx} from {img_url}")
                        resp = requests.get(img_url, headers=headers, stream=True, timeout=20)
                        if resp.status_code == 200:
                            with open(filepath, 'wb') as f:
                                for chunk in resp.iter_content(8192):
                                    f.write(chunk)
                            downloaded_count += 1
                            logger.info(f"Successfully downloaded image {idx}")
                        else:
                            logger.warning(f"Failed to download image {idx} for {note_id}: {resp.status_code} URL: {img_url}")
                    except Exception as e:
                        logger.warning(f"Error downloading image {idx} for {note_id}: {e}")
            else:
                logger.info(f"No image_list found for note {note_id}")
            
            # 2. 下载视频
            if note_data.get('note_type') == '视频' and note_data.get('video_addr'):
                video_url = note_data['video_addr']
                filename = f"video.mp4"
                filepath = os.path.join(note_dir, filename)
                
                logger.info(f"Downloading video for note {note_id} from {video_url}")
                
                if not (os.path.exists(filepath) and os.path.getsize(filepath) > 1024):
                    try:
                        resp = requests.get(video_url, headers=headers, stream=True, timeout=60)
                        if resp.status_code == 200:
                            with open(filepath, 'wb') as f:
                                for chunk in resp.iter_content(1024*1024): # 1MB chunks
                                    f.write(chunk)
                            downloaded_count += 1
                            logger.info(f"Successfully downloaded video for {note_id}")
                        else:
                            logger.warning(f"Failed to download video for {note_id}: {resp.status_code}")
                    except Exception as e:
                        logger.warning(f"Error downloading video for {note_id}: {e}")
                else:
                    logger.info(f"Skipping existing video for note {note_id}")
            elif note_data.get('note_type') == '视频':
                logger.warning(f"Video note {note_id} missing video_addr")

            if downloaded_count > 0:
                logger.info(f"Archived {downloaded_count} media files for note {note_id}")
            else:
                logger.info(f"No media files downloaded for note {note_id} (maybe already exists or empty list)")
                
        except Exception as e:
            logger.error(f"Error in _download_all_media for {note_id}: {e}")

    @staticmethod
    def _save_note(note_data, download_media=False):
        """保存笔记到数据库（使用merge避免重复插入）
        
        【重要说明】
        列表页API只返回部分数据（点赞数）,不返回收藏、评论、转发数和发布时间。
        当这些字段为None时,表示"数据不可用",应保留数据库中的现有值。
        """
        try:
            # 【关键检查】确保note_id不为空
            note_id = note_data.get('note_id')
            if not note_id:
                logger.info(f"Skipping note save: note_id is empty. Data: {note_data.get('title', 'unknown')}")
                return

            # 计算封面（远程 + 本地缓存）
            cover_remote = note_data.get('cover_remote') or note_data.get('video_cover')
            if not cover_remote:
                imgs = note_data.get('image_list') or []
                cover_remote = imgs[0] if len(imgs) > 0 else None
            cover_local = SyncService._download_cover(cover_remote, note_id) if cover_remote else None
            
            # 使用merge实现upsert语义,避免唯一约束冲突
            note = Note.query.filter_by(note_id=note_id).first()
            
            if note:
                # 更新现有笔记 - 只更新非None的字段
                note.nickname = note_data['nickname']
                note.avatar = note_data['avatar']
                note.title = note_data['title']
                # desc可能为空字符串,但不应覆盖现有描述（除非详情页明确返回）
                if note_data['desc'] is not None and note_data['desc'] != '':
                    note.desc = note_data['desc']
                note.type = note_data['note_type']
                
                # 【关键逻辑】互动数据:只有非None时才更新
                # liked_count列表页有返回,始终更新
                if note_data['liked_count'] is not None:
                    note.liked_count = note_data['liked_count']
                # collected_count、comment_count、share_count列表页不返回（为None）,保留原值
                if note_data['collected_count'] is not None:
                    note.collected_count = note_data['collected_count']
                if note_data['comment_count'] is not None:
                    note.comment_count = note_data['comment_count']
                if note_data['share_count'] is not None:
                    note.share_count = note_data['share_count']
                
                # 【关键逻辑】发布时间:列表页不返回（为None）,保留原值
                if note_data['upload_time'] is not None:
                    note.upload_time = note_data['upload_time']
                
                # 媒体数据:只有非空时才更新
                if note_data['video_addr']:
                    note.video_addr = note_data['video_addr']
                # 【关键修复】图片列表:只有当新列表数量大于现有数量时才更新
                # 防止列表页的1张封面覆盖详情页的完整图片列表
                if note_data['image_list']:
                    new_img_count = len(note_data['image_list'])
                    try:
                        old_img_list = json.loads(note.image_list) if note.image_list else []
                        old_img_count = len(old_img_list)
                    except:
                        old_img_count = 0
                    # 只有新列表更多时才更新，或者旧列表为空/只有1张时也更新
                    if new_img_count > old_img_count or old_img_count <= 1:
                        note.image_list = json.dumps(note_data['image_list'])
                        logger.info(f"Updated image_list for {note_id}: {old_img_count} -> {new_img_count} images")
                if note_data['tags']:
                    note.tags = json.dumps(note_data['tags'])
                if note_data['ip_location']:
                    note.ip_location = note_data['ip_location']
                if cover_remote:
                    note.cover_remote = cover_remote
                if cover_local:
                    note.cover_local = cover_local
                    
                note.last_updated = datetime.utcnow()
            else:
                # 创建新笔记 - None值转为默认值
                note = Note(
                    note_id=note_id,
                    user_id=note_data['user_id'],
                    nickname=note_data['nickname'],
                    avatar=note_data['avatar'],
                    title=note_data['title'],
                    desc=note_data['desc'] or '',
                    type=note_data['note_type'],
                    liked_count=note_data['liked_count'] if note_data['liked_count'] is not None else 0,
                    collected_count=note_data['collected_count'] if note_data['collected_count'] is not None else 0,
                    comment_count=note_data['comment_count'] if note_data['comment_count'] is not None else 0,
                    share_count=note_data['share_count'] if note_data['share_count'] is not None else 0,
                    upload_time=note_data['upload_time'] or '',
                    video_addr=note_data['video_addr'] or '',
                    image_list=json.dumps(note_data['image_list']) if note_data['image_list'] else '[]',
                    tags=json.dumps(note_data['tags']) if note_data['tags'] else '[]',
                    ip_location=note_data['ip_location'] or '',
                    cover_remote=cover_remote or '',
                    cover_local=cover_local or '',
                )
                db.session.add(note)
            
            db.session.commit()
            
            if download_media:
                logger.info(f"Triggering media download for note {note_id}")
                SyncService._download_all_media(note_id, note_data)
            else:
                logger.info(f"Skipping media download for note {note_id} (download_media=False)")
                
        except Exception as e:
            # 发生异常时回滚session,避免PendingRollbackError
            db.session.rollback()
            logger.info(f"Error saving note {note_data.get('note_id')}: {e}")
            # 重新抛出异常让上层处理
            raise

    @staticmethod
    def _download_cover(remote_url, note_id):
        """下载封面到本地并返回可访问的API路径"""
        if not remote_url:
            return None
        try:
            Config.init_paths()
            parsed = urlparse(remote_url)
            ext = os.path.splitext(parsed.path)[1]
            if not ext or len(ext) > 5:
                ext = '.jpg'
            filename = f"{note_id}_cover{ext}"
            filepath = os.path.join(Config.MEDIA_PATH, filename)
            
            # 检查文件是否存在且大小正常（>1KB）
            if os.path.exists(filepath) and os.path.getsize(filepath) > 1024:
                return f"/api/media/{filename}"
            
            headers = get_common_headers()
            # 增加重试机制
            for attempt in range(3):
                try:
                    resp = requests.get(remote_url, headers=headers, stream=True, timeout=15)
                    if resp.status_code == 200:
                        with open(filepath, 'wb') as f:
                            for chunk in resp.iter_content(8192):
                                if chunk:
                                    f.write(chunk)
                        logger.info(f"Successfully downloaded cover for {note_id}")
                        return f"/api/media/{filename}"
                    elif resp.status_code == 403:
                        logger.warning(f"Download cover 403 Forbidden for {note_id}, attempt {attempt+1}")
                        time.sleep(1)
                    else:
                        logger.warning(f"Download cover failed ({resp.status_code}) for {note_id}")
                except Exception as dl_err:
                    logger.warning(f"Download attempt {attempt+1} failed: {dl_err}")
                    time.sleep(1)
                    
        except Exception as e:
            logger.error(f"Download cover error for {note_id}: {e}")
        return None

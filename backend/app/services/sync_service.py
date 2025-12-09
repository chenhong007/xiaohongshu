"""
同步服务 - 处理笔记数据同步
"""
import json
import time
import threading
from datetime import datetime
from flask import current_app

from ..extensions import db
from ..models import Account, Note, Cookie


class SyncService:
    """同步服务类"""
    
    @staticmethod
    def get_cookie_str():
        """获取有效的 Cookie 字符串"""
        cookie = Cookie.query.filter_by(is_active=True, is_valid=True).first()
        if cookie:
            return cookie.cookie_str
        
        # 从配置获取
        from ..config import Config
        return Config.XHS_COOKIES
    
    @staticmethod
    def start_sync(account_ids):
        """启动后台同步任务"""
        from .. import create_app
        app = create_app()
        
        thread = threading.Thread(target=SyncService._run_sync, args=(app, account_ids))
        thread.daemon = True
        thread.start()
    
    @staticmethod
    def _run_sync(app, account_ids):
        """在后台线程中执行同步"""
        with app.app_context():
            SyncService._sync_accounts(account_ids)
    
    @staticmethod
    def _sync_accounts(account_ids):
        """同步账号的笔记数据"""
        print(f"Starting sync for accounts: {account_ids}")
        
        cookie_str = SyncService.get_cookie_str()
        if not cookie_str:
            print("No valid cookie found")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': '未找到有效的 Cookie，请先登录小红书'},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        try:
            from apis.xhs_pc_apis import XHS_Apis
            from xhs_utils.data_util import handle_note_info
            xhs_apis = XHS_Apis()
        except Exception as e:
            error_msg = f"初始化 API 失败: {e}"
            print(f"Failed to init XHS APIs: {e}")
            Account.query.filter(Account.id.in_(account_ids)).update(
                {'status': 'failed', 'error_message': error_msg},
                synchronize_session=False
            )
            db.session.commit()
            return
        
        for acc_id in account_ids:
            try:
                account = Account.query.get(acc_id)
                if not account:
                    continue
                
                # 更新状态为处理中，清除之前的错误信息
                account.status = 'processing'
                account.progress = 0
                account.error_message = None
                db.session.commit()
                
                # 构建用户 URL，包含 xsec_token 用于 API 验证
                xsec_token = account.xsec_token or ''
                warning_msg = None
                
                # 如果没有 xsec_token，尝试获取
                if not xsec_token:
                    print(f"No xsec_token for account {account.user_id}, attempting to fetch...")
                    try:
                        success_token, msg_token, fetched_token = xhs_apis.get_user_xsec_token(account.user_id, cookie_str)
                        if success_token and fetched_token:
                            xsec_token = fetched_token
                            # 保存到数据库以便后续使用
                            account.xsec_token = xsec_token
                            db.session.commit()
                            print(f"Successfully fetched xsec_token for {account.user_id}")
                        else:
                            print(f"Could not fetch xsec_token: {msg_token}")
                    except Exception as e:
                        print(f"Error fetching xsec_token: {e}")
                
                if xsec_token:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}?xsec_token={xsec_token}&xsec_source=pc_search'
                else:
                    user_url = f'https://www.xiaohongshu.com/user/profile/{account.user_id}'
                    warning_msg = f"缺少 xsec_token，可能导致同步失败"
                    print(f"Warning: No xsec_token for account {account.user_id}, sync may fail")
                
                # 获取用户所有笔记列表
                success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookie_str)
                
                if not success:
                    error_msg = f"获取笔记列表失败: {msg}"
                    if warning_msg:
                        error_msg = f"{warning_msg}。{error_msg}"
                    print(f"Failed to get notes for {account.user_id}: {msg}")
                    account.status = 'failed'
                    account.error_message = error_msg
                    db.session.commit()
                    continue
                
                total = len(all_note_info)
                account.total_msgs = total
                account.loaded_msgs = 0
                db.session.commit()
                
                # 处理每个笔记
                # 使用账号的 xsec_token 作为后备，如果笔记自带 xsec_token 则优先使用
                account_xsec_token = account.xsec_token or ''
                for idx, simple_note in enumerate(all_note_info):
                    note_id = simple_note.get('note_id')
                    # 优先使用笔记自带的 xsec_token（由 get_user_all_notes 添加），否则使用账号的
                    note_xsec_token = simple_note.get('xsec_token') or account_xsec_token
                    note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note_xsec_token}"
                    
                    success, msg, note_detail = xhs_apis.get_note_info(note_url, cookie_str)
                    
                    if success and note_detail:
                        try:
                            # 安全访问嵌套数据，防止 NoneType 错误
                            data = note_detail.get('data')
                            if data and data.get('items') and len(data['items']) > 0:
                                note_data = data['items'][0]
                                note_data['url'] = note_url
                                cleaned_data = handle_note_info(note_data)
                                SyncService._save_note(cleaned_data)
                            else:
                                print(f"Note {note_id} has no valid data")
                        except Exception as e:
                            print(f"Error parsing note {note_id}: {e}")
                    
                    # 更新进度
                    account.loaded_msgs = idx + 1
                    account.progress = int(((idx + 1) / total) * 100) if total > 0 else 100
                    db.session.commit()
                    
                    # 请求间隔，避免被封
                    time.sleep(1)
                
                # 完成同步
                account.status = 'completed'
                account.last_sync = datetime.utcnow()
                db.session.commit()
                
            except Exception as e:
                print(f"Error syncing account {acc_id}: {e}")
                # 先回滚 session，避免 PendingRollbackError
                db.session.rollback()
                try:
                    account = Account.query.get(acc_id)
                    if account:
                        account.status = 'failed'
                        account.error_message = f"同步出错: {str(e)}"
                        db.session.commit()
                except Exception as inner_e:
                    print(f"Error updating account status: {inner_e}")
                    db.session.rollback()
    
    @staticmethod
    def _save_note(note_data):
        """保存笔记到数据库（使用 merge 避免重复插入）"""
        try:
            # 使用 merge 实现 upsert 语义，避免唯一约束冲突
            note = Note.query.filter_by(note_id=note_data['note_id']).first()
            
            if note:
                # 更新现有笔记
                note.nickname = note_data['nickname']
                note.avatar = note_data['avatar']
                note.title = note_data['title']
                note.desc = note_data['desc']
                note.type = note_data['note_type']
                note.liked_count = note_data['liked_count']
                note.collected_count = note_data['collected_count']
                note.comment_count = note_data['comment_count']
                note.share_count = note_data['share_count']
                note.upload_time = note_data['upload_time']
                note.video_addr = note_data['video_addr']
                note.image_list = json.dumps(note_data['image_list'])
                note.tags = json.dumps(note_data['tags'])
                note.ip_location = note_data['ip_location']
                note.last_updated = datetime.utcnow()
            else:
                # 创建新笔记
                note = Note(
                    note_id=note_data['note_id'],
                    user_id=note_data['user_id'],
                    nickname=note_data['nickname'],
                    avatar=note_data['avatar'],
                    title=note_data['title'],
                    desc=note_data['desc'],
                    type=note_data['note_type'],
                    liked_count=note_data['liked_count'],
                    collected_count=note_data['collected_count'],
                    comment_count=note_data['comment_count'],
                    share_count=note_data['share_count'],
                    upload_time=note_data['upload_time'],
                    video_addr=note_data['video_addr'],
                    image_list=json.dumps(note_data['image_list']),
                    tags=json.dumps(note_data['tags']),
                    ip_location=note_data['ip_location'],
                )
                db.session.add(note)
            
            db.session.commit()
        except Exception as e:
            # 发生异常时回滚 session，避免 PendingRollbackError
            db.session.rollback()
            print(f"Error saving note {note_data.get('note_id')}: {e}")
            # 重新抛出异常让上层处理
            raise


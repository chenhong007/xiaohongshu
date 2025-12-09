import sys
import os
import sqlite3
import json
import time
import threading
from datetime import datetime
from flask import Flask, jsonify, request

# Import modules from local backend structure
try:
    from apis.xhs_pc_apis import XHS_Apis
    from xhs_utils.common_util import init, save_cookie_to_db
    from xhs_utils.data_util import handle_note_info
    from xhs_utils.cookie_util import trans_cookies
except ImportError as e:
    print(f"Error importing modules: {e}")
    XHS_Apis = None

app = Flask(__name__)
# Database path relative to this file
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'xhs_data.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT UNIQUE,
                name TEXT,
                avatar TEXT,
                last_sync TEXT,
                total_msgs INTEGER DEFAULT 0,
                loaded_msgs INTEGER DEFAULT 0,
                progress INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending'
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                note_id TEXT PRIMARY KEY,
                user_id TEXT,
                nickname TEXT,
                avatar TEXT,
                title TEXT,
                desc TEXT,
                type TEXT,
                liked_count INTEGER,
                collected_count INTEGER,
                comment_count INTEGER,
                share_count INTEGER,
                upload_time TEXT,
                video_addr TEXT,
                image_list TEXT,
                tags TEXT,
                ip_location TEXT,
                last_updated TEXT
            )
        ''')
        conn.commit()

init_db()

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    with get_db() as conn:
        rows = conn.execute('SELECT * FROM accounts ORDER BY id DESC').fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/accounts', methods=['POST'])
def add_account():
    data = request.json
    user_id = data.get('user_id')
    name = data.get('name')
    avatar = data.get('avatar')
    
    if not user_id:
        return jsonify({'error': 'Missing user_id'}), 400
        
    with get_db() as conn:
        try:
            conn.execute('INSERT INTO accounts (user_id, name, avatar) VALUES (?, ?, ?)',
                         (user_id, name, avatar))
            conn.commit()
            return jsonify({'success': True})
        except sqlite3.IntegrityError:
             return jsonify({'error': 'User already exists'}), 409

@app.route('/api/accounts/<int:account_id>/sync', methods=['POST'])
def sync_account(account_id):
    thread = threading.Thread(target=run_sync, args=([account_id],))
    thread.start()
    return jsonify({'success': True, 'message': 'Sync started'})

@app.route('/api/accounts/sync-batch', methods=['POST'])
def sync_batch():
    ids = request.json.get('ids', [])
    if not ids:
        return jsonify({'error': 'No ids provided'}), 400
    
    # Reset status for all batch ids
    with get_db() as conn:
        placeholders = ','.join('?' * len(ids))
        sql = f'UPDATE accounts SET status = "pending", progress = 0 WHERE id IN ({placeholders})'
        conn.execute(sql, ids)
        conn.commit()

    thread = threading.Thread(target=run_sync, args=(ids,))
    thread.start()
    return jsonify({'success': True, 'message': 'Batch sync started'})

@app.route('/api/accounts/sync-all', methods=['POST'])
def sync_all():
    with get_db() as conn:
        rows = conn.execute('SELECT id FROM accounts').fetchall()
        ids = [row['id'] for row in rows]
        
        # Reset all to pending
        if ids:
            conn.execute('UPDATE accounts SET status = "pending", progress = 0')
            conn.commit()
    
    thread = threading.Thread(target=run_sync, args=(ids,))
    thread.start()
    return jsonify({'success': True, 'message': 'Sync all started'})

@app.route('/api/reset', methods=['POST'])
def reset_db():
    with get_db() as conn:
        conn.execute('DELETE FROM accounts')
        conn.execute('DELETE FROM notes')
        conn.commit()
    return jsonify({'success': True})

@app.route('/api/user/me', methods=['GET'])
def get_user_me():
    try:
        cookies_str, _ = init()
        if not cookies_str:
             print("No cookies found in environment")
             return jsonify({'is_connected': False})
             
        xhs_apis = XHS_Apis()
        success, msg, user_info = xhs_apis.get_user_self_info(cookies_str)
        
        print(f"User info check result: success={success}, msg={msg}")
        if user_info:
            print(f"User info data keys: {user_info.get('data', {}).keys()}")
        
        if success and user_info.get('data'):
             data = user_info['data']
             # Try to get basic info if it exists (structure variation handling)
             basic_info = data.get('basic_info', data)
             
             # Try multiple fields for nickname
             nickname = basic_info.get('nickname') or data.get('nickname') or '未知用户'
             
             # Try multiple fields for avatar (images, head_photo, avatar)
             avatar = basic_info.get('images') or basic_info.get('avatar') or basic_info.get('head_photo') or \
                      data.get('images') or data.get('avatar') or data.get('head_photo') or ''
                      
             # Try multiple fields for user_id
             user_id = basic_info.get('red_id') or basic_info.get('user_id') or \
                       data.get('red_id') or data.get('user_id') or ''

             return jsonify({
                 'is_connected': True,
                 'nickname': nickname,
                 'avatar': avatar,
                 'user_id': user_id
             })
        else:
             print(f"Failed to get user info or no data. Response: {user_info}")
             return jsonify({'is_connected': False})
             
    except Exception as e:
        print(f"Error checking user login status: {e}")
        return jsonify({'is_connected': False})

@app.route('/api/cookie/manual', methods=['POST'])
def manual_cookie():
    data = request.json
    cookies_str = data.get('cookies')
    if not cookies_str:
        return jsonify({'error': 'No cookies provided'}), 400

    try:
        # 1. Validate cookie format first
        cookies_dict = trans_cookies(cookies_str)
        if 'a1' not in cookies_dict:
             return jsonify({'detail': "无效的 Cookie：缺少核心字段 'a1'，请确保复制了完整的 Cookie 字符串"}), 400

        # 2. Try to verify credentials by getting self info
        xhs_apis = XHS_Apis()
        success, msg, user_info = xhs_apis.get_user_self_info(cookies_str)
        
        if not success:
             return jsonify({'detail': f"Cookie 验证失败: {msg}"}), 400
        
        # 3. Extract user info for saving
        user_id = None
        nickname = None
        avatar = None
        if user_info and user_info.get('data'):
            info_data = user_info['data']
            basic_info = info_data.get('basic_info', info_data)
            user_id = basic_info.get('red_id') or basic_info.get('user_id') or info_data.get('red_id') or info_data.get('user_id')
            nickname = basic_info.get('nickname') or info_data.get('nickname')
            avatar = basic_info.get('images') or basic_info.get('avatar') or info_data.get('images') or info_data.get('avatar')
             
        # 4. Save valid cookies to database
        if save_cookie_to_db(cookies_str, user_id, nickname, avatar):
            return jsonify({'success': True, 'message': 'Cookie 保存成功'})
        else:
            return jsonify({'detail': 'Cookie 保存到数据库失败'}), 500
            
    except Exception as e:
        print(f"Error validating cookie: {e}")
        return jsonify({'detail': f"验证过程发生错误: {str(e)}"}), 500

def save_note_to_db(note_data):
    with get_db() as conn:
        conn.execute('''
            INSERT OR REPLACE INTO notes (
                note_id, user_id, nickname, avatar, title, desc, type,
                liked_count, collected_count, comment_count, share_count,
                upload_time, video_addr, image_list, tags, ip_location, last_updated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            note_data['note_id'],
            note_data['user_id'],
            note_data['nickname'],
            note_data['avatar'],
            note_data['title'],
            note_data['desc'],
            note_data['note_type'],
            note_data['liked_count'],
            note_data['collected_count'],
            note_data['comment_count'],
            note_data['share_count'],
            note_data['upload_time'],
            note_data['video_addr'],
            json.dumps(note_data['image_list']),
            json.dumps(note_data['tags']),
            note_data['ip_location'],
            datetime.now().isoformat()
        ))
        conn.commit()

def run_sync(account_ids):
    print(f"Starting sync for accounts: {account_ids}")
    
    try:
        cookies_str, _ = init()
        xhs_apis = XHS_Apis()
    except Exception as e:
        print(f"Failed to init spider: {e}")
        # Mark all accounts as failed if init fails
        with get_db() as conn:
            placeholders = ','.join('?' * len(account_ids))
            sql = f'UPDATE accounts SET status = "failed" WHERE id IN ({placeholders})'
            conn.execute(sql, account_ids)
            conn.commit()
        return

    for acc_id in account_ids:
        try:
            with get_db() as conn:
                conn.execute('UPDATE accounts SET status = ?, progress = 0 WHERE id = ?', ('processing', acc_id))
                conn.commit()
                cursor = conn.execute('SELECT user_id FROM accounts WHERE id = ?', (acc_id,))
                row = cursor.fetchone()
                if not row:
                    continue
                user_id = row[0]

            # 获取账户的 xsec_token
            with get_db() as conn:
                cursor = conn.execute('SELECT xsec_token FROM accounts WHERE id = ?', (acc_id,))
                token_row = cursor.fetchone()
                account_xsec_token = token_row[0] if token_row and token_row[0] else ''
            
            # 如果没有 xsec_token，尝试获取
            if not account_xsec_token:
                print(f"No xsec_token for account {user_id}, attempting to fetch...")
                try:
                    success_token, msg_token, fetched_token = xhs_apis.get_user_xsec_token(user_id, cookies_str)
                    if success_token and fetched_token:
                        account_xsec_token = fetched_token
                        # 保存到数据库以便后续使用
                        with get_db() as conn:
                            conn.execute('UPDATE accounts SET xsec_token = ? WHERE id = ?', (account_xsec_token, acc_id))
                            conn.commit()
                        print(f"Successfully fetched xsec_token for {user_id}")
                    else:
                        print(f"Could not fetch xsec_token: {msg_token}")
                except Exception as e:
                    print(f"Error fetching xsec_token: {e}")
            
            # 构建用户 URL，包含 xsec_token
            if account_xsec_token:
                user_url = f'https://www.xiaohongshu.com/user/profile/{user_id}?xsec_token={account_xsec_token}&xsec_source=pc_search'
            else:
                user_url = f'https://www.xiaohongshu.com/user/profile/{user_id}'
                print(f"Warning: No xsec_token for account {user_id}, sync may fail")
            
            # 1. Get all notes
            success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookies_str)
            if not success:
                print(f"Failed to get notes for {user_id}: {msg}")
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET status = ?, error_message = ? WHERE id = ?', ('failed', f'获取笔记列表失败: {msg}', acc_id))
                    conn.commit()
                continue

            total = len(all_note_info)
            with get_db() as conn:
                conn.execute('UPDATE accounts SET total_msgs = ?, loaded_msgs = 0 WHERE id = ?', (total, acc_id))
                conn.commit()

            # 2. Process each note
            processed = 0
            for simple_note in all_note_info:
                note_id = simple_note.get('note_id')
                # 优先使用笔记自带的 xsec_token，否则使用账号的
                note_xsec_token = simple_note.get('xsec_token') or account_xsec_token
                note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={note_xsec_token}"
                
                success, msg, note_detail = xhs_apis.get_note_info(note_url, cookies_str)
                if success and note_detail:
                    try:
                        # 安全访问嵌套数据，防止 NoneType 错误
                        data = note_detail.get('data')
                        if data and data.get('items') and len(data['items']) > 0:
                            note_data = data['items'][0]
                            note_data['url'] = note_url
                            cleaned_data = handle_note_info(note_data)
                            save_note_to_db(cleaned_data)
                        else:
                            print(f"Note {note_id} has no valid data")
                    except Exception as e:
                        print(f"Error parsing note {note_id}: {e}")
                
                processed += 1
                progress = int((processed / total) * 100) if total > 0 else 100
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET loaded_msgs = ?, progress = ? WHERE id = ?', (processed, progress, acc_id))
                    conn.commit()
                
                time.sleep(1) # Be nice to API

            with get_db() as conn:
                conn.execute('UPDATE accounts SET status = ?, last_sync = ? WHERE id = ?',
                             ('completed', datetime.now().isoformat(), acc_id))
                conn.commit()

        except Exception as e:
            print(f"Error syncing account {acc_id}: {e}")
            with get_db() as conn:
                conn.execute('UPDATE accounts SET status = ? WHERE id = ?', ('failed', acc_id))
                conn.commit()

@app.route('/api/login', methods=['POST'])
def login():
    # Placeholder for login script triggering
    # In a real scenario, this might launch a selenium script or similar
    # For now, we rely on manual cookie input or pre-configured environment
    return jsonify({'detail': '自动登录脚本暂未启用，请使用手动输入 Cookie 功能'}), 501

if __name__ == '__main__':
    print("Starting backend server on port 8000...")
    app.run(port=8000, debug=True, use_reloader=False)


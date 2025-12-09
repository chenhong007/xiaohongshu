import sys
import os
import sqlite3
import json
import time
import threading
from datetime import datetime
from flask import Flask, jsonify, request

# Adjust path to import Spider_XHS modules
current_dir = os.path.dirname(os.path.abspath(__file__))
spider_path = os.path.join(current_dir, '..', 'Spider_XHS')
sys.path.append(spider_path)

try:
    from apis.xhs_pc_apis import XHS_Apis
    from xhs_utils.common_util import init
    from xhs_utils.data_util import handle_note_info
except ImportError as e:
    print(f"Error importing Spider_XHS: {e}")
    XHS_Apis = None

app = Flask(__name__)
DB_PATH = os.path.join(current_dir, 'xhs_data.db')

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
    
    thread = threading.Thread(target=run_sync, args=(ids,))
    thread.start()
    return jsonify({'success': True, 'message': 'Batch sync started'})

@app.route('/api/accounts/sync-all', methods=['POST'])
def sync_all():
    with get_db() as conn:
        rows = conn.execute('SELECT id FROM accounts').fetchall()
        ids = [row['id'] for row in rows]
    
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

            user_url = f'https://www.xiaohongshu.com/user/profile/{user_id}'
            
            # 1. Get all notes
            success, msg, all_note_info = xhs_apis.get_user_all_notes(user_url, cookies_str)
            if not success:
                print(f"Failed to get notes for {user_id}: {msg}")
                with get_db() as conn:
                    conn.execute('UPDATE accounts SET status = ? WHERE id = ?', ('failed', acc_id))
                    conn.commit()
                continue

            total = len(all_note_info)
            with get_db() as conn:
                conn.execute('UPDATE accounts SET total_msgs = ?, loaded_msgs = 0 WHERE id = ?', (total, acc_id))
                conn.commit()

            # 2. Process each note
            processed = 0
            for simple_note in all_note_info:
                note_id = simple_note['note_id']
                xsec_token = simple_note.get('xsec_token')
                note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}"
                
                success, msg, note_detail = xhs_apis.get_note_info(note_url, cookies_str)
                if success:
                    try:
                        note_detail = note_detail['data']['items'][0]
                        note_detail['url'] = note_url
                        cleaned_data = handle_note_info(note_detail)
                        save_note_to_db(cleaned_data)
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

if __name__ == '__main__':
    print("Starting backend server on port 8000...")
    app.run(port=8000, debug=True, use_reloader=False)


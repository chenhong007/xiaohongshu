from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from models import SessionLocal, Account, Note, reset_db, init_db
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json
import os
import subprocess
import sys
from apis.xhs_pc_apis import XHS_Apis
from xhs_utils.data_util import handle_note_info

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models
class AccountBase(BaseModel):
    name: str
    user_id: str
    avatar: Optional[str] = None
    total_msgs: int = 0
    loaded_msgs: int = 0
    progress: int = 0
    status: str = 'pending'

class AccountCreate(AccountBase):
    pass

class AccountOut(AccountBase):
    id: int
    last_sync: Optional[datetime] = None

    class Config:
        from_attributes = True

class UserInfo(BaseModel):
    nickname: str
    avatar: Optional[str] = None
    is_connected: bool = False

class CookieInput(BaseModel):
    cookies: str

def get_user_config():
    config_path = os.path.join(os.path.dirname(__file__), 'user_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def sync_account_task(account_id: int):
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return

        config = get_user_config()
        cookies = config.get('cookies')
        if not cookies:
            print("No cookies found in config")
            account.status = 'error'
            db.commit()
            return

        # Update status to processing
        account.status = 'processing'
        account.progress = 0
        db.commit()

        xhs_apis = XHS_Apis()
        
        # 1. Fetch all note list first to get total count
        print(f"Starting sync for account {account.name} ({account.user_id})")
        
        all_notes_simple = []
        cursor = ''
        page_count = 0
        while True:
            # Get user notes list
            success, msg, res_json = xhs_apis.get_user_note_info(account.user_id, cursor, cookies)
            if not success:
                print(f"Failed to get user notes: {msg}")
                # If fail on first page, maybe error
                if page_count == 0:
                     account.status = 'error'
                     db.commit()
                     return
                break
            
            data = res_json.get('data', {})
            notes = data.get('notes', [])
            all_notes_simple.extend(notes)
            
            print(f"Fetched page {page_count}, {len(notes)} notes. Total so far: {len(all_notes_simple)}")
            
            if data.get('has_more') and data.get('cursor'):
                cursor = str(data['cursor'])
                page_count += 1
            else:
                break
        
        account.total_msgs = len(all_notes_simple)
        account.loaded_msgs = 0
        db.commit()
        
        print(f"Total notes found: {account.total_msgs}")
        
        # 2. Fetch details for each note
        for index, simple_note in enumerate(all_notes_simple):
            note_id = simple_note.get('note_id') or simple_note.get('id')
            if not note_id:
                continue
                
            # Construct fake url for API call
            note_url_fake = f"https://www.xiaohongshu.com/explore/{note_id}"
            
            success, msg, note_detail_res = xhs_apis.get_note_info(note_url_fake, cookies)
            if success:
                try:
                    items = note_detail_res.get('data', {}).get('items', [])
                    if items:
                        note_raw = items[0]
                        processed_note = handle_note_info(note_raw)
                        
                        # Save to DB
                        db_note = db.query(Note).filter(Note.link == processed_note['note_url']).first()
                        if not db_note:
                            # Parse time
                            try:
                                create_time = datetime.strptime(processed_note['upload_time'], "%Y-%m-%d %H:%M:%S")
                            except:
                                create_time = datetime.now()

                            db_note = Note(
                                title=processed_note['title'],
                                link=processed_note['note_url'],
                                cover=processed_note['video_cover'] if processed_note['note_type'] == '视频' else (processed_note['image_list'][0] if processed_note['image_list'] else None),
                                create_time=create_time,
                                read_count=processed_note['liked_count'], 
                                user_id=account.id
                            )
                            db.add(db_note)
                        else:
                            # Update existing note
                            db_note.read_count = processed_note['liked_count']
                            db_note.title = processed_note['title']
                        
                        account.loaded_msgs += 1
                        if account.total_msgs > 0:
                            account.progress = int((account.loaded_msgs / account.total_msgs) * 100)
                        
                        # Commit every 5 notes or on last one
                        if index % 5 == 0 or index == len(all_notes_simple) - 1:
                            db.commit()
                            
                except Exception as e:
                    print(f"Error processing note {note_id}: {e}")
            else:
                print(f"Failed to get note detail {note_id}: {msg}")
                
        account.status = 'completed'
        account.last_sync = datetime.now()
        account.progress = 100
        db.commit()
        print(f"Sync completed for {account.name}")

    except Exception as e:
        print(f"Sync task error: {e}")
        if account:
            account.status = 'error'
            db.commit()
    finally:
        db.close()

def sync_all_accounts_task():
    db = SessionLocal()
    try:
        accounts = db.query(Account).all()
        account_ids = [acc.id for acc in accounts]
    finally:
        db.close()
    
    print(f"Starting sync for all {len(account_ids)} accounts")
    for account_id in account_ids:
        sync_account_task(account_id)
    print("Sync all accounts completed")

# Routes
@app.on_event("startup")
def startup_event():
    init_db()

@app.get("/api/search/users")
def search_users_api(keyword: str):
    config = get_user_config()
    cookies = config.get('cookies')
    if not cookies:
        raise HTTPException(status_code=401, detail="Please login first")
    
    xhs_apis = XHS_Apis()
    success, msg, res_json = xhs_apis.search_user(keyword, cookies)
    
    if not success:
        raise HTTPException(status_code=500, detail=f"Search failed: {msg}")
    
    users = res_json.get('data', {}).get('users', [])
    return users

@app.post("/api/reset")
def reset_database():
    """Clear all tables and re-create them"""
    reset_db()
    return {"message": "Database reset successfully"}

@app.get("/api/accounts", response_model=List[AccountOut])
def read_accounts(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    accounts = db.query(Account).offset(skip).limit(limit).all()
    return accounts

@app.post("/api/accounts", response_model=AccountOut)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    existing_account = db.query(Account).filter(Account.user_id == account.user_id).first()
    if existing_account:
        existing_account.name = account.name
        existing_account.avatar = account.avatar
        db.commit()
        db.refresh(existing_account)
        return existing_account

    db_account = Account(**account.dict())
    db_account.last_sync = datetime.now()
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@app.post("/api/accounts/{account_id}/sync")
def sync_account(account_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    
    background_tasks.add_task(sync_account_task, account_id)
    return {"message": "Sync started"}

@app.post("/api/accounts/sync-all")
def sync_all_accounts(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_all_accounts_task)
    return {"message": "Sync all started"}

@app.get("/api/user/me", response_model=UserInfo)
def get_current_user():
    config_path = os.path.join(os.path.dirname(__file__), 'user_config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return UserInfo(
                    nickname=data.get('nickname', 'Unknown'),
                    avatar=data.get('avatar', ''),
                    is_connected=True
                )
        except Exception:
            pass
    
    return UserInfo(nickname="", is_connected=False)

@app.post("/api/cookie/manual")
def manual_cookie_login(input_data: CookieInput):
    """Manually set cookies"""
    cookies_str = input_data.cookies.strip()
    if not cookies_str:
        raise HTTPException(status_code=400, detail="Cookies cannot be empty")
        
    xhs_apis = XHS_Apis()
    try:
        success, msg, user_info = xhs_apis.get_user_self_info(cookies_str)
        if not success:
            print(f"v1 api failed: {msg}, trying v2...")
            success, msg, user_info = xhs_apis.get_user_self_info2(cookies_str)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API call failed: {str(e)}")
    
    if success:
        try:
            data = user_info.get('data', {})
            basic_info = data.get('basic_info', {})
            nickname = basic_info.get('nickname')
            avatar = basic_info.get('images')
            
            if not nickname:
                nickname = data.get('nickname')
            if not avatar:
                avatar = data.get('images') or data.get('avatar')
            
            if not nickname:
                nickname = '未知用户'

            if not avatar:
                avatar = ''
            
            user_config = {
                "nickname": nickname,
                "avatar": avatar,
                "cookies": cookies_str,
                "updated_at": str(datetime.now())
            }
            
            config_path = os.path.join(os.path.dirname(__file__), 'user_config.json')
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(user_config, f, ensure_ascii=False, indent=4)
                
            return {"message": "Cookie set successfully", "user": {"nickname": nickname, "avatar": avatar}}
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse user info: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail=f"Invalid cookies or failed to fetch user info: {msg}")

@app.post("/api/login")
def login_from_chrome():
    """Trigger the login script to fetch cookies from Chrome"""
    try:
        result = subprocess.run(
            [sys.executable, "main.py", "--browser_cookie", "Chrome", "--update_settings"],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            if "Cookie 获取失败" in result.stdout or "Cookie 获取失败" in result.stderr:
                 raise HTTPException(status_code=400, detail="从 Chrome 获取 Cookie 失败，请确保 Chrome 已打开并登录小红书")
            
            config_path = os.path.join(os.path.dirname(__file__), 'user_config.json')
            if os.path.exists(config_path):
                return {"message": "Login successful", "details": result.stdout}
            else:
                 raise HTTPException(status_code=500, detail="登录脚本执行成功但未生成配置文件")
        else:
            error_msg = result.stderr or result.stdout
            raise HTTPException(status_code=500, detail=f"登录脚本执行失败: {error_msg}")
            
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

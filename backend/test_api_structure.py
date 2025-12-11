
import json
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from apis.xhs_pc_apis import XHS_Apis
from extensions import db
from flask import Flask
from config import Config
from models import Cookie

def test_note_detail():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    
    with app.app_context():
        # Get Cookie
        cookie_obj = Cookie.query.filter_by(is_active=True).first()
        if not cookie_obj:
            print("No active cookie found!")
            return
            
        cookie_str = cookie_obj.get_cookie_str()
        print(f"Using Cookie (prefix): {cookie_str[:20]}...")
        
        xhs_apis = XHS_Apis()
        
        # Test Note ID (Video)
        note_id = "675bc860000000000702d849" # Random or specific one? Let's use the one from debug_db output if possible.
        # From previous output: 6915ec3b00000000040138e5
        # Wait, 691... looks like a futuristic ID, maybe timestamp based? 
        # Actually the previous output was: 6915ec3b00000000040138e5
        # Let's try to search for the user first to get a fresh valid note ID
        
        user_url = "https://www.xiaohongshu.com/user/profile/5ae6916f4eacab18b7523538"
        print(f"Fetching notes for user: {user_url}")
        
        success, msg, notes = xhs_apis.get_user_all_notes(user_url, cookie_str)
        
        if success and notes:
            print(f"Got {len(notes)} notes.")
            first_note = notes[0]
            print("--- First Note (List Data) ---")
            print(json.dumps(first_note, ensure_ascii=False, indent=2))
            
            # Now fetch detail
            note_id = first_note.get('note_id') or first_note.get('id')
            xsec_token = first_note.get('xsec_token', '')
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}?xsec_token={xsec_token}"
            
            print(f"\nFetching detail for {note_id}...")
            success, msg, detail = xhs_apis.get_note_info(note_url, cookie_str)
            
            if success:
                print("--- Note Detail (Raw Data) ---")
                # Print only relevant parts to avoid huge output
                if 'data' in detail and 'items' in detail['data']:
                    item = detail['data']['items'][0]
                    print(json.dumps(item, ensure_ascii=False, indent=2))
                else:
                    print(json.dumps(detail, ensure_ascii=False, indent=2))
            else:
                print(f"Failed to fetch detail: {msg}")
        else:
            print(f"Failed to fetch user notes: {msg}")

if __name__ == "__main__":
    test_note_detail()



import sqlite3
import os

def check_db():
    # Use absolute path or relative to current dir
    db_path = 'xhs_data.db' 
    if not os.path.exists(db_path):
        print(f"Database not found at {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 1. 查找账号
    print("--- Checking Account ---")
    cursor.execute("SELECT id, user_id, name, status, error_message, total_msgs, loaded_msgs, last_sync FROM accounts WHERE name LIKE '%向阳乔木%'")
    account = cursor.fetchone()
    
    if account:
        print(f"Found Account: ID={account[0]}, UserID={account[1]}, Name={account[2]}")
        print(f"Status: {account[3]}")
        print(f"Error Message: {account[4]}")
        print(f"Total Msgs: {account[5]}, Loaded: {account[6]}")
        print(f"Last Sync: {account[7]}")
        
        user_id = account[1]
        
        # 2. 查找笔记
        print("\n--- Checking Notes ---")
        cursor.execute(f"SELECT count(*) FROM notes WHERE user_id = '{user_id}'")
        count = cursor.fetchone()[0]
        print(f"Total notes in DB for this user: {count}")
        
        if count > 0:
            cursor.execute(f"SELECT note_id, title, type, cover_local, image_list FROM notes WHERE user_id = '{user_id}' LIMIT 3")
            print("\nSample Notes:")
            for note in cursor.fetchall():
                print(f"- [{note[2]}] {note[0]} - {note[1][:20]}...")
                print(f"  Cover Local: {note[3]}")
                print(f"  Image List len: {len(note[4]) if note[4] else 0}")
    else:
        print("Account '向阳乔木' not found in database.")

    conn.close()

if __name__ == "__main__":
    check_db()



import sqlite3
import os
import requests

def get_common_headers():
    return {
        "authority": "sns-img-qc.xhscdn.com", # 针对图片域名的 host
        "accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "accept-language": "zh-CN,zh;q=0.9",
        "cache-control": "no-cache",
        "pragma": "no-cache",
        "referer": "https://www.xiaohongshu.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

def check_db_and_download():
    db_path = 'xhs_data.db'
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("--- Checking First Note ---")
    cursor.execute("SELECT note_id, title, cover_remote FROM notes WHERE user_id = '5ae6916f4eacab18b7523538' LIMIT 1")
    note = cursor.fetchone()
    
    if note:
        note_id = note[0]
        title = note[1]
        url = note[2]
        print(f"Note: {title}")
        print(f"Remote URL: {url}")
        
        if url:
            print("\n--- Testing Download ---")
            headers = get_common_headers()
            try:
                # 尝试直连
                print(f"Attempting download from {url}...")
                resp = requests.get(url, headers=headers, stream=True, timeout=10)
                print(f"Status Code: {resp.status_code}")
                if resp.status_code == 200:
                    print("Download SUCCESS!")
                    print(f"Content Type: {resp.headers.get('content-type')}")
                    print(f"Content Length: {resp.headers.get('content-length')}")
                    # Try writing to a test file
                    with open(f"test_{note_id}.jpg", "wb") as f:
                        for chunk in resp.iter_content(1024):
                            f.write(chunk)
                    print("Saved to test file.")
                else:
                    print(f"Download FAILED. Headers: {resp.headers}")
            except Exception as e:
                print(f"Download ERROR: {e}")
        else:
            print("No remote URL to test.")
    else:
        print("No notes found.")

    conn.close()

if __name__ == "__main__":
    check_db_and_download()


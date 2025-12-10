import sqlite3

conn = sqlite3.connect('backend/xhs_data.db')
try:
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, name, xsec_token, status, error_message FROM account")
    rows = cursor.fetchall()
    print("ID | user_id | name | xsec_token | status | error")
    print("-" * 100)
    for r in rows:
        token_preview = str(r[3])[:40] + "..." if r[3] else "None"
        print(f"{r[0]} | {r[1]} | {r[2]} | {token_preview} | {r[4]} | {r[5]}")
except Exception as e:
    print(f"Error: {e}")
finally:
    conn.close()


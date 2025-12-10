import sqlite3
import pandas as pd

conn = sqlite3.connect('backend/xhs_data.db')
try:
    df = pd.read_sql_query("SELECT id, user_id, name, status, total_msgs, loaded_msgs, error_message FROM accounts", conn)
    print(df)
except Exception as e:
    print(e)
finally:
    conn.close()


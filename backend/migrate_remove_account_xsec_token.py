#!/usr/bin/env python3
"""
删除 accounts 表中的 xsec_token 列
运行: python3 migrate_remove_account_xsec_token.py
"""
import os
import sqlite3
import shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'xhs_data.db')

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"数据库不存在: {DB_PATH}")
        return
    
    backup = f"{DB_PATH}.bak_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"备份到: {backup}")
    shutil.copy2(DB_PATH, backup)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'xsec_token' not in columns:
        print("xsec_token 列不存在，无需迁移")
        conn.close()
        return
    
    new_cols = [c for c in columns if c != 'xsec_token']
    cols_str = ', '.join(new_cols)
    
    cursor.execute(f"CREATE TABLE accounts_new AS SELECT {cols_str} FROM accounts")
    cursor.execute("DROP TABLE accounts")
    cursor.execute("ALTER TABLE accounts_new RENAME TO accounts")
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_accounts_user_id ON accounts (user_id)")
    
    conn.commit()
    conn.close()
    print("Done! xsec_token 列已删除")

if __name__ == '__main__':
    confirm = input("确认删除 accounts.xsec_token? (y/N): ")
    if confirm.lower() == 'y':
        migrate()

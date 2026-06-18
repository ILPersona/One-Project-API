import sqlite3
from datetime import datetime

DB_NAME = "ai_bot_database.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            referrer_id INTEGER,
            source_tag TEXT,
            tokens INTEGER DEFAULT 5,
            reg_date TEXT
        )
    ''')
    conn.commit()
    conn.close()

def add_new_user(user_id, username, first_name, referrer_id, source_tag):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if user is None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO users (user_id, username, first_name, referrer_id, source_tag, reg_date) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, first_name, referrer_id, source_tag, now)
        )
        # Если пришел по рефералке, начисляем бонусы пригласившему
        if referrer_id:
            cursor.execute("UPDATE users SET tokens = tokens + 3 WHERE user_id = ?", (referrer_id,))
        conn.commit()
        conn.close()
        return True # Юзер новый
    
    conn.close()
    return False # Юзер уже был в базе

def get_tokens(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT tokens FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 5

def use_token(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET tokens = tokens - 1 WHERE user_id = ? AND tokens > 0", (user_id,))
    conn.commit()
    conn.close()

def get_stats():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users")
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0
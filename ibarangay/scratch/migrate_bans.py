import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), '..', 'ibarangay.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE user ADD COLUMN warning_count INTEGER DEFAULT 0")
        print("Added warning_count")
    except Exception as e:
        print(f"Error adding warning_count: {e}")
    
    try:
        cursor.execute("ALTER TABLE user ADD COLUMN banned_until DATETIME")
        print("Added banned_until")
    except Exception as e:
        print(f"Error adding banned_until: {e}")
    
    conn.commit()
    conn.close()
    print("Database updated.")
else:
    print(f"Database not found at {db_path}")

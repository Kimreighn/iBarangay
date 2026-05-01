import os
import shutil
import sqlite3


def count_sqlite_users(db_path):
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return 0

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user'")
        if not cur.fetchone():
            return 0
        cur.execute("SELECT COUNT(*) FROM user")
        row = cur.fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def find_richest_sqlite_backup(backup_dir):
    if not os.path.isdir(backup_dir):
        return None, 0

    best_path = None
    best_count = 0
    best_mtime = -1.0

    for name in os.listdir(backup_dir):
        if not name.endswith('.db'):
            continue

        path = os.path.join(backup_dir, name)
        count = count_sqlite_users(path)
        mtime = os.path.getmtime(path)

        if count > best_count or (count == best_count and mtime > best_mtime):
            best_path = path
            best_count = count
            best_mtime = mtime

    return best_path, best_count


def restore_sqlite_backup_if_richer(active_db_path, backup_dir):
    current_count = count_sqlite_users(active_db_path)
    best_backup_path, best_backup_count = find_richest_sqlite_backup(backup_dir)

    if not best_backup_path:
        return False, current_count, best_backup_count

    if current_count <= 1 and best_backup_count > current_count:
        shutil.copy2(best_backup_path, active_db_path)
        return True, current_count, best_backup_count

    return False, current_count, best_backup_count

import os
import sqlite3
import tempfile
import unittest

from sqlite_safety import count_sqlite_users, find_richest_sqlite_backup, restore_sqlite_backup_if_richer


def make_db(path, user_count):
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.execute(
            '''
            CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                username TEXT,
                password_hash TEXT,
                full_name TEXT,
                role TEXT,
                is_approved INTEGER
            )
            '''
        )
        for idx in range(1, user_count + 1):
            cur.execute(
                "INSERT INTO user (id, username, password_hash, full_name, role, is_approved) VALUES (?, ?, ?, ?, ?, ?)",
                (idx, f'user{idx}@test.com', 'hash', f'User {idx}', 'resident', 1)
            )
        conn.commit()
    finally:
        conn.close()


class SQLiteSafetyTestCase(unittest.TestCase):
    def test_counts_users_in_sqlite_db(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'sample.db')
            make_db(db_path, 3)
            self.assertEqual(count_sqlite_users(db_path), 3)

    def test_finds_richest_backup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db1 = os.path.join(tmpdir, 'a.db')
            db2 = os.path.join(tmpdir, 'b.db')
            make_db(db1, 1)
            make_db(db2, 4)

            best_path, best_count = find_richest_sqlite_backup(tmpdir)
            self.assertEqual(best_path, db2)
            self.assertEqual(best_count, 4)

    def test_restores_richer_backup_when_active_db_only_has_seed_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            active_db = os.path.join(tmpdir, 'ibarangay.db')
            backup_dir = os.path.join(tmpdir, 'backups')
            os.makedirs(backup_dir, exist_ok=True)

            make_db(active_db, 1)
            make_db(os.path.join(backup_dir, 'full_backup.db'), 5)

            restored, old_count, backup_count = restore_sqlite_backup_if_richer(active_db, backup_dir)

            self.assertTrue(restored)
            self.assertEqual(old_count, 1)
            self.assertEqual(backup_count, 5)
            self.assertEqual(count_sqlite_users(active_db), 5)


if __name__ == '__main__':
    unittest.main()

from flask import Flask, render_template, session, redirect, url_for
from models import db, User, Family
from datetime import timedelta
from werkzeug.security import generate_password_hash
from sqlalchemy import inspect, text
import os
import shutil
from routes import main
from database_config import BACKUP_DIR, SQLITE_DB_PATH, ensure_database_exists, get_database_uri, get_sqlite_uri
from sqlite_safety import restore_sqlite_backup_if_richer
from time_utils import ph_now

app = Flask(__name__)
DEFAULT_WEB_PUSH_PUBLIC_KEY = 'BGOJPVjj5huchwlymCYkadIR_4E68johAzqtQiMWVoo5MPazKEYJHyDHkdWbbixtsLmDVnbqZMAFCG9BaulHFCQ'
DEFAULT_WEB_PUSH_PRIVATE_KEY = 'X-dbSXigy9xjNngldZlwzcpBDEUZMjla0ama_8nRCIA'
app.config['SECRET_KEY'] = 'ibarangay-super-secret-key-2026'
app.config['SQLALCHEMY_DATABASE_URI'] = get_database_uri()
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True}
app.config['WEB_PUSH_PUBLIC_KEY'] = os.environ.get('IBARANGAY_WEB_PUSH_PUBLIC_KEY', DEFAULT_WEB_PUSH_PUBLIC_KEY).strip()
app.config['WEB_PUSH_PRIVATE_KEY'] = os.environ.get('IBARANGAY_WEB_PUSH_PRIVATE_KEY', DEFAULT_WEB_PUSH_PRIVATE_KEY).strip()
app.config['WEB_PUSH_SUBJECT'] = os.environ.get('IBARANGAY_WEB_PUSH_SUBJECT', 'mailto:alerts@ibarangay.local').strip()

# Persistent Session Logic
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30) 

app.register_blueprint(main)

db.init_app(app)


def ensure_runtime_schema():
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if 'rating' not in tables:
        return

    rating_columns = {column['name'] for column in inspector.get_columns('rating')}
    if 'rater_id' not in rating_columns:
        with db.engine.begin() as conn:
            conn.execute(text('ALTER TABLE rating ADD COLUMN rater_id INTEGER NULL'))

    if 'announcement' in tables:
        announcement_columns = {column['name'] for column in inspector.get_columns('announcement')}
        if 'target_users' not in announcement_columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE announcement ADD COLUMN target_users TEXT NULL'))
        if 'target_puroks' not in announcement_columns:
            with db.engine.begin() as conn:
                conn.execute(text('ALTER TABLE announcement ADD COLUMN target_puroks TEXT NULL'))


def snapshot_database():
    if not os.path.exists(SQLITE_DB_PATH) or os.path.getsize(SQLITE_DB_PATH) == 0:
        return

    os.makedirs(BACKUP_DIR, exist_ok=True)

    latest_backup = os.path.join(BACKUP_DIR, 'ibarangay_latest.db')
    shutil.copy2(SQLITE_DB_PATH, latest_backup)

    timestamp = ph_now().strftime('%Y%m%d_%H%M%S')
    dated_backup = os.path.join(BACKUP_DIR, f'ibarangay_{timestamp}.db')
    shutil.copy2(SQLITE_DB_PATH, dated_backup)

    backups = sorted(
        [
            os.path.join(BACKUP_DIR, name)
            for name in os.listdir(BACKUP_DIR)
            if name.startswith('ibarangay_') and name.endswith('.db') and name != 'ibarangay_latest.db'
        ],
        key=os.path.getmtime,
        reverse=True
    )
    for old_backup in backups[10:]:
        try:
            os.remove(old_backup)
        except OSError:
            pass

with app.app_context():
    if app.config['SQLALCHEMY_DATABASE_URI'] == get_sqlite_uri():
        restored_backup, old_count, backup_count = restore_sqlite_backup_if_richer(SQLITE_DB_PATH, BACKUP_DIR)
        if restored_backup:
            print(f"Restored SQLite backup before startup: users {old_count} -> {backup_count}")
        snapshot_database()
    ensure_database_exists(app.config['SQLALCHEMY_DATABASE_URI'])
    db.create_all()
    ensure_runtime_schema()
    # Seed Superadmin
    if not User.query.filter_by(role='superadmin').first():
        hashed = generate_password_hash('camerain26')
        sa = User(username='kquima@ssct.edu.ph', password_hash=hashed, full_name='Main Admin', role='superadmin', is_approved=True)
        db.session.add(sa)
        db.session.commit()

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

import os
from urllib.parse import quote_plus
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
SQLITE_DB_PATH = os.path.join(BASE_DIR, 'ibarangay.db')
BACKUP_DIR = os.path.join(BASE_DIR, 'scratch', 'db_backups')


def get_sqlite_uri():
    return 'sqlite:///' + SQLITE_DB_PATH


def normalize_database_url(url):
    if not url:
        return None
    if url.startswith('mysql://'):
        return 'mysql+pymysql://' + url[len('mysql://'):]
    return url


def build_mysql_uri():
    host = os.getenv('MYSQL_HOST')
    if not host:
        return None

    user = os.getenv('MYSQL_USER', 'root')
    password = os.getenv('MYSQL_PASSWORD', '')
    port = os.getenv('MYSQL_PORT', '3306')
    database = os.getenv('MYSQL_DATABASE', 'ibarangay')
    charset = os.getenv('MYSQL_CHARSET', 'utf8mb4')

    auth_user = quote_plus(user)
    if password:
        auth = f"{auth_user}:{quote_plus(password)}"
    else:
        auth = auth_user

    return f"mysql+pymysql://{auth}@{host}:{port}/{database}?charset={charset}"


def get_database_uri():
    direct_url = normalize_database_url(os.getenv('DATABASE_URL'))
    if direct_url:
        return direct_url

    mysql_uri = build_mysql_uri()
    if mysql_uri:
        return mysql_uri

    return get_sqlite_uri()


def is_sqlite_uri(uri):
    return uri.startswith('sqlite:///') or uri == 'sqlite:///:memory:'


def ensure_database_exists(database_uri):
    if is_sqlite_uri(database_uri):
        return

    url = make_url(database_uri)
    database_name = url.database
    server_engine = create_engine(url.set(database=None), pool_pre_ping=True)

    try:
        with server_engine.connect() as conn:
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{database_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
    finally:
        server_engine.dispose()

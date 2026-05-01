import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database_config import SQLITE_DB_PATH, ensure_database_exists, get_database_uri, get_sqlite_uri, is_sqlite_uri
from models import (
    db,
    Announcement,
    Emergency,
    Event,
    Family,
    FinancialReport,
    HistoryLog,
    Post,
    PostLike,
    Rating,
    ReliefDistribution,
    Summons,
    User,
)


MODEL_MIGRATION_ORDER = [
    Family,
    User,
    Event,
    FinancialReport,
    ReliefDistribution,
    Announcement,
    Post,
    Rating,
    Emergency,
    Summons,
    PostLike,
    HistoryLog,
]


def clone_row(model, row):
    return model(**{column.name: getattr(row, column.name) for column in model.__table__.columns})


def migrate():
    if not os.path.exists(SQLITE_DB_PATH):
        raise SystemExit(f"SQLite database not found: {SQLITE_DB_PATH}")

    target_uri = get_database_uri()
    if is_sqlite_uri(target_uri):
        raise SystemExit(
            "MySQL is not configured yet. Set MYSQL_HOST / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DATABASE "
            "or DATABASE_URL first."
        )

    ensure_database_exists(target_uri)

    source_engine = create_engine(get_sqlite_uri())
    target_engine = create_engine(target_uri, pool_pre_ping=True)

    try:
        db.Model.metadata.create_all(target_engine)

        SourceSession = sessionmaker(bind=source_engine)
        TargetSession = sessionmaker(bind=target_engine)

        with SourceSession() as source_session, TargetSession() as target_session:
            if target_session.query(User).count() > 0:
                raise SystemExit(
                    "Target MySQL database already contains users. Migration stopped to avoid overwriting current data."
                )

            for model in MODEL_MIGRATION_ORDER:
                rows = source_session.query(model).all()
                for row in rows:
                    target_session.add(clone_row(model, row))
                target_session.commit()
                print(f"Migrated {len(rows)} rows from {model.__tablename__}")
    finally:
        source_engine.dispose()
        target_engine.dispose()


if __name__ == '__main__':
    migrate()

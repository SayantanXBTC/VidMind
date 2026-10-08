"""SQLAlchemy engine and session setup."""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

def _normalize_url(url: str) -> str:
    """Point bare postgres URLs (as Supabase/Railway hand them out) at psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalize_url(settings.DATABASE_URL)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    # Pooled cloud databases drop idle connections; check before use.
    pool_pre_ping=not IS_SQLITE,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """Add columns new model fields introduced after tables already existed.

    SQLite has no ALTER-based migration tooling wired up yet, so on startup
    we diff each mapped table against its live schema and ADD COLUMN for
    anything missing. Safe for nullable/defaulted columns only.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"))
                logger.info("Migrated table %s: added column %s", table.name, column.name)


def init_db() -> None:
    from app.models import video  # noqa: F401  (register models on Base)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    with engine.begin() as conn:
        # Videos created before accounts existed belong to the local user.
        conn.execute(text("UPDATE videos SET user_id = 'local' WHERE user_id IS NULL"))

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from core.config import settings


def _configure_engine(engine):
    """Apply SQLite-specific pragmas when using SQLite; no-op for PostgreSQL."""
    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_conn, _):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


def _make_engine():
    url = settings.database_url
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # PostgreSQL: connection pool sizing for the multi-process Docker setup
        kwargs["pool_size"] = 10
        kwargs["max_overflow"] = 20
        kwargs["pool_pre_ping"] = True
    engine = create_engine(url, **kwargs)
    _configure_engine(engine)
    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Session:
    """FastAPI dependency — yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables that don't yet exist. Use Alembic for subsequent migrations."""
    from core.models import Base  # noqa: F401 — registers all models
    Base.metadata.create_all(bind=engine)
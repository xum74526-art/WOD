from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

_engine_kwargs = {"pool_pre_ping": True, "echo": False}
if settings.DATABASE_URL.startswith("sqlite"):
    # FastAPI endpoints and background collectors run in different worker
    # threads.  Give short concurrent writes time to finish, while WAL (enabled
    # by init_db.py) keeps readers from being blocked by market synchronization.
    _engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.DATABASE_URL, **_engine_kwargs)


if engine.dialect.name == "sqlite":
    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()


SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def _fence_authenticated_write(db):
    user_id = db.info.get("authenticated_user_id")
    if user_id is not None and not db.info.get("account_deletion_worker"):
        from app.services.account_lifecycle import lock_active_user
        lock_active_user(db, user_id)


@event.listens_for(Session, "before_flush")
def _account_deletion_flush_fence(db, _flush_context, _instances):
    if db.new or db.dirty or db.deleted:
        _fence_authenticated_write(db)
        if db.new and not db.info.get("account_deletion_worker"):
            from app.services.account_lifecycle import fence_new_business_owners
            fence_new_business_owners(db)


@event.listens_for(Session, "do_orm_execute")
def _account_deletion_bulk_fence(state):
    if state.is_update or state.is_delete or state.is_insert:
        _fence_authenticated_write(state.session)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

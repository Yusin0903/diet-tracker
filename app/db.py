"""SQLAlchemy engine / session,建表。

自用工具:啟動時 create_all()(IF NOT EXISTS 語意),不另外導入 Alembic。
"""
from typing import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.settings import settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def init_engine() -> None:
    """建立 engine + session factory,並確保資料表存在。"""
    global _engine, _SessionLocal
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL 尚未設定")
    _engine = create_engine(
        settings.database_url, pool_size=settings.db_max_conn, pool_pre_ping=True
    )
    _SessionLocal = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)

    from app.models import Base  # 延後匯入,確保所有 model 已註冊到 Base

    Base.metadata.create_all(_engine)


def get_engine() -> Engine:
    assert _engine is not None, "engine 尚未初始化,請先呼叫 init_engine()"
    return _engine


def get_db() -> Iterator[Session]:
    """FastAPI 依賴:借一個 Session,成功則 commit,例外則 rollback,用完關閉。"""
    assert _SessionLocal is not None, "engine 尚未初始化,請先呼叫 init_engine()"
    db = _SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

"""Postgres 連線池、建表。

自用工具:啟動時跑一次建表 SQL(IF NOT EXISTS),不另外導入 Alembic。
"""
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

from app.settings import settings

_pool: ThreadedConnectionPool | None = None
SCHEMA_PATH = Path(__file__).parent / "sql" / "schema.sql"


def init_pool() -> None:
    """建立連線池並確保資料表存在。"""
    global _pool
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL 尚未設定")
    _pool = ThreadedConnectionPool(
        minconn=1, maxconn=settings.db_max_conn, dsn=settings.database_url
    )
    _create_tables()


def _create_tables() -> None:
    ddl = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_cursor(commit=True) as cur:
        cur.execute(ddl)


@contextmanager
def get_conn():
    """從池子借一條連線,用完歸還。"""
    assert _pool is not None, "連線池尚未初始化,請先呼叫 init_pool()"
    conn = _pool.getconn()
    try:
        yield conn
    finally:
        _pool.putconn(conn)


@contextmanager
def get_cursor(commit: bool = False):
    """方便的 cursor context,回傳 dict 形式的列。"""
    with get_conn() as conn:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            yield cur
            # commit 寫入;讀取路徑也要 rollback,否則連線會以
            # 「idle in transaction」歸還連線池(持有快照、擋 VACUUM)。
            if commit:
                conn.commit()
            else:
                conn.rollback()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()

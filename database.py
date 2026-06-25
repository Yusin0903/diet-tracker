"""Postgres 連線、建表、seed。

自用工具:啟動時跑一次建表 SQL(IF NOT EXISTS),不另外導入 Alembic。
"""
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool

import config

_pool: ThreadedConnectionPool | None = None


def init_pool() -> None:
    """建立連線池並確保資料表存在。"""
    global _pool
    if not config.DATABASE_URL:
        raise RuntimeError("DATABASE_URL 尚未設定")
    # maxconn 需 >= FastAPI 同步端點的執行緒併發數,否則高併發時 getconn
    # 會丟 PoolError。可用 DB_MAX_CONN 覆蓋。
    max_conn = int(os.environ.get("DB_MAX_CONN", "40"))
    _pool = ThreadedConnectionPool(minconn=1, maxconn=max_conn, dsn=config.DATABASE_URL)
    _create_tables()


def _create_tables() -> None:
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        ddl = f.read()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()


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

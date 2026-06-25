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
    _pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=config.DATABASE_URL)
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
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def seed_foods_for_user(user_id: int) -> None:
    """為新會員塞入預設常用食物。"""
    with get_cursor(commit=True) as cur:
        for food in config.SEED_FOODS:
            cur.execute(
                """
                INSERT INTO foods (user_id, name, calories, protein_g)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (user_id, name) DO NOTHING
                """,
                (user_id, food["name"], food["calories"], food["protein_g"]),
            )

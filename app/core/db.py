# app/core/db.py
import os
import asyncpg
import certifi
import ssl
from contextlib import asynccontextmanager

_pool: asyncpg.Pool | None = None

async def init_db_pool() -> None:
    global _pool
    if _pool is not None:
        return
    ctx = ssl.create_default_context(cafile=certifi.where())
    _pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),
        ssl=ctx,
        min_size=int(os.getenv("DB_POOL_MIN", "1")),
        max_size=int(os.getenv("DB_POOL_MAX", "10")),
    )

async def close_db_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None

@asynccontextmanager
async def db_conn():
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Call init_db_pool() on startup.")
    conn = await _pool.acquire()
    try:
        yield conn
    finally:
        await _pool.release(conn)

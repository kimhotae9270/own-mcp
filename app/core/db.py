import psycopg2
from contextlib import contextmanager
from app.core.config import DATABASE_URL

@contextmanager
def db_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

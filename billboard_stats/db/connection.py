"""PostgreSQL connection pool management."""

import os

import psycopg2
from psycopg2 import pool

_connection_pool = None


def get_pool() -> pool.ThreadedConnectionPool:
    """Return the shared connection pool, creating it on first call."""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        _connection_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", 5432)),
            dbname=os.environ.get("PGDATABASE", "billboard"),
            user=os.environ.get("PGUSER", "postgres"),
            password=os.environ.get("PGPASSWORD", ""),
        )
    return _connection_pool


def get_conn():
    """Get a connection from the pool."""
    return get_pool().getconn()


def put_conn(conn):
    """Return a connection to the pool."""
    get_pool().putconn(conn)


def close_pool():
    """Close the connection pool."""
    global _connection_pool
    if _connection_pool and not _connection_pool.closed:
        _connection_pool.closeall()
        _connection_pool = None


def execute_query(query: str, params=None, fetch: bool = True):
    """Execute a query and optionally return results."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


def execute_script(sql: str):
    """Execute a multi-statement SQL script."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)

"""PostgreSQL connection pool management."""

import os

import psycopg2
from psycopg2 import pool

_connection_pool = None


def _get_setting(key: str, default: str = "") -> str:
    """Read a config value from Streamlit secrets (if available) or env vars."""
    try:
        import streamlit as st
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)


def get_pool() -> pool.ThreadedConnectionPool:
    """Return the shared connection pool, creating it on first call."""
    global _connection_pool
    if _connection_pool is None or _connection_pool.closed:
        conn_kwargs = dict(
            minconn=1,
            maxconn=10,
            host=_get_setting("PGHOST", "localhost"),
            port=int(_get_setting("PGPORT", "5432")),
            dbname=_get_setting("PGDATABASE", "billboard"),
            user=_get_setting("PGUSER", "postgres"),
            password=_get_setting("PGPASSWORD", ""),
        )
        sslmode = _get_setting("PGSSLMODE")
        if sslmode:
            conn_kwargs["sslmode"] = sslmode
        _connection_pool = pool.ThreadedConnectionPool(**conn_kwargs)
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
                if cur.description is None:
                    return []
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return [dict(zip(columns, row)) for row in rows]
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        put_conn(conn)


def resolve_chart_id(slug: str) -> int:
    """Resolve a chart slug to its registry ``chart_id`` (an int; Pitfall 1).

    The single shared slug->id resolver for the read-side services (M-03): the
    parametric ``valid_weeks_cte`` binds a ``%s::int`` chart_id, NOT a slug, so
    every query resolves its slug to an int first. Raises ``ValueError`` if the
    slug is unknown (a missing registry row would otherwise silently produce
    empty results). Mirrors the ETL-side ``stats_builder._resolve_chart_id`` /
    ``loader._resolve_chart_id`` (which take an explicit conn).
    """
    rows = execute_query("SELECT id FROM charts WHERE slug = %s;", (slug,))
    if not rows or rows[0]["id"] is None:
        raise ValueError(f"No chart registered for slug {slug!r}")
    return rows[0]["id"]


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

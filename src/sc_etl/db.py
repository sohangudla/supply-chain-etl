"""Database helpers: engine creation, running SQL files, fast bulk COPY."""
from __future__ import annotations

import io
import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from .config import DBConfig

log = logging.getLogger(__name__)


def get_engine(cfg: DBConfig | None = None, database: str | None = None) -> Engine:
    cfg = cfg or DBConfig()
    return create_engine(cfg.url(database), pool_pre_ping=True, future=True)


def run_sql_file(conn: Connection, path: Path) -> None:
    """Execute a .sql file that may contain several statements."""
    sql = Path(path).read_text(encoding="utf-8")
    # exec_driver_sql passes the whole script to psycopg2, which handles
    # multiple statements separated by semicolons.
    conn.exec_driver_sql(sql)
    log.debug("Executed %s", Path(path).name)


def copy_dataframe(conn: Connection, df: pd.DataFrame, table: str) -> int:
    """Bulk-load a DataFrame with PostgreSQL COPY (much faster than INSERTs).

    Runs inside the caller's transaction, so it is rolled back on failure.
    """
    if df.empty:
        return 0
    buf = io.StringIO()
    # NULLs are written as empty unquoted fields; COPY CSV treats those as NULL.
    df.to_csv(buf, index=False, header=False)
    buf.seek(0)
    cols = ", ".join(f'"{c}"' for c in df.columns)
    cursor = conn.connection.cursor()
    try:
        cursor.copy_expert(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv)", buf)
    finally:
        cursor.close()
    return len(df)


def scalar(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params).scalar()

"""Watermark = the latest order_purchase_timestamp already loaded.

Each run only processes orders strictly newer than the watermark. The
watermark is advanced in the SAME transaction as the fact load, so either
both happen or neither does: a crash can never leave the watermark ahead
of the data (which would silently skip orders).
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection


def get_watermark(conn: Connection, pipeline: str) -> pd.Timestamp | None:
    value = conn.execute(
        text("SELECT watermark_value FROM audit.etl_watermark WHERE pipeline_name = :p"),
        {"p": pipeline},
    ).scalar()
    return pd.Timestamp(value) if value is not None else None


def set_watermark(conn: Connection, pipeline: str, value: pd.Timestamp, run_id: int) -> None:
    conn.execute(
        text("""
            INSERT INTO audit.etl_watermark (pipeline_name, watermark_value, run_id, updated_at)
            VALUES (:p, :v, :r, now())
            ON CONFLICT (pipeline_name) DO UPDATE
            SET watermark_value = GREATEST(audit.etl_watermark.watermark_value, EXCLUDED.watermark_value),
                run_id = EXCLUDED.run_id, updated_at = now()
        """),
        {"p": pipeline, "v": value.to_pydatetime(), "r": run_id},
    )


def reset_watermark(conn: Connection, pipeline: str) -> None:
    conn.execute(text("DELETE FROM audit.etl_watermark WHERE pipeline_name = :p"), {"p": pipeline})

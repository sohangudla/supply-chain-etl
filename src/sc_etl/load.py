"""LOAD: staging tables -> warehouse star schema, plus audit records."""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Connection

from .config import SQL_DIR
from .db import copy_dataframe, run_sql_file
from .quality import QualityReport

log = logging.getLogger(__name__)

STAGING_TABLES = ["dim_customer", "dim_product", "dim_seller", "dim_date",
                  "fact_order_items", "fact_payments"]


class LoadIntegrityError(RuntimeError):
    """Fact rows were lost during surrogate-key lookup."""


@dataclass
class LoadResult:
    fact_inserted: int
    fact_updated: int
    payments_inserted: int
    payments_updated: int


def ensure_schema(conn: Connection) -> None:
    for f in sorted((SQL_DIR / "ddl").glob("*.sql")):
        run_sql_file(conn, f)


def load_star_schema(conn: Connection, run_id: int, frames: dict[str, pd.DataFrame]) -> LoadResult:
    """frames: staging-shaped DataFrames keyed by STAGING_TABLES names."""
    conn.exec_driver_sql("TRUNCATE " + ", ".join(f"staging.{t}" for t in STAGING_TABLES))
    for t in STAGING_TABLES:
        n = copy_dataframe(conn, frames[t], f"staging.{t}")
        log.info("Staged %-18s %8d rows", t, n)

    run_sql_file(conn, SQL_DIR / "load" / "upsert_dimensions.sql")

    sql = (SQL_DIR / "load" / "upsert_fact_order_items.sql").read_text(encoding="utf-8")
    ins, upd = conn.execute(text(sql), {"run_id": run_id}).one()
    sql = (SQL_DIR / "load" / "upsert_fact_payments.sql").read_text(encoding="utf-8")
    p_ins, p_upd = conn.execute(text(sql), {"run_id": run_id}).one()

    # Integrity guard: every staged fact row must have found its dimension keys.
    # An INNER JOIN that silently drops rows is a classic warehouse bug.
    for name, staged, loaded in (("fact_order_items", len(frames["fact_order_items"]), ins + upd),
                                 ("fact_payments", len(frames["fact_payments"]), p_ins + p_upd)):
        if staged != loaded:
            raise LoadIntegrityError(f"{name}: staged {staged} rows but loaded {loaded}")

    log.info("fact_order_items: %d inserted, %d updated", ins, upd)
    log.info("fact_payments   : %d inserted, %d updated", p_ins, p_upd)
    return LoadResult(ins, upd, p_ins, p_upd)


def write_quality_audit(conn: Connection, run_id: int, report: QualityReport) -> None:
    results = pd.DataFrame([{
        "run_id": run_id, "check_name": r.check_name, "table_name": r.table_name,
        "check_type": r.check_type, "severity": r.severity, "rows_checked": r.rows_checked,
        "rows_failed": r.rows_failed, "passed": r.passed} for r in report.results])
    copy_dataframe(conn, results, "audit.dq_check_results")
    if not report.rejected.empty:
        rej = report.rejected.assign(run_id=run_id)[["run_id", "table_name", "record_key", "check_name"]]
        copy_dataframe(conn, rej, "audit.rejected_records")

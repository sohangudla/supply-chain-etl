"""Pipeline orchestrator:  EXTRACT -> VALIDATE -> TRANSFORM -> LOAD.

Transaction boundaries (important for safe reruns):
  T1  create run record                      (committed immediately)
  T2  extract CSV -> raw                     (raw is truncate+reload)
  T3  data-quality results + rejected rows   (committed even if load later fails,
                                              so failures can be investigated)
  T4  staging -> warehouse upserts + watermark advance   (ALL OR NOTHING)
  T5  mark run SUCCESS / FAILED

Usage:
  python -m sc_etl.pipeline --source-dir data/landing/batch_01
  python -m sc_etl.pipeline --full-refresh
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from . import transform as T
from .config import DEFAULT_SOURCE_DIR, MAX_REJECT_RATIO, PIPELINE_NAME
from .db import get_engine
from .extract import extract_to_raw, read_raw
from .load import ensure_schema, load_star_schema, write_quality_audit
from .log import setup_logging
from .quality import enforce_reject_threshold, run_quality_checks
from .watermark import get_watermark, reset_watermark, set_watermark

log = logging.getLogger("sc_etl.pipeline")

TABLES_FOR_TRANSFORM = ["orders", "order_items", "order_payments", "order_reviews",
                        "customers", "products", "sellers", "category_translation"]


def _start_run(engine: Engine, source_dir: Path) -> int:
    with engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO audit.pipeline_runs (pipeline_name, source_dir) "
                 "VALUES (:p, :s) RETURNING run_id"),
            {"p": PIPELINE_NAME, "s": str(source_dir)}).scalar_one()


def _finish_run(engine: Engine, run_id: int, status: str, **fields) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in fields)
    with engine.begin() as conn:
        conn.execute(text(f"UPDATE audit.pipeline_runs SET status = :status, finished_at = now()"
                          f"{', ' + sets if sets else ''} WHERE run_id = :run_id"),
                     {"status": status, "run_id": run_id, **fields})


def build_staging_frames(accepted: dict[str, pd.DataFrame],
                         watermark: pd.Timestamp | None) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Pure transform step: accepted raw frames -> staging-shaped frames.
    Returns (frames, new_orders)."""
    orders = T.clean_orders(accepted["orders"])
    new_orders = T.filter_incremental(orders, watermark)
    fact_items = T.build_fact_order_items(new_orders, accepted["order_items"],
                                          accepted["order_reviews"])
    fact_pay = T.build_fact_payments(new_orders, accepted["order_payments"])
    frames = {
        "dim_customer": T.build_dim_customer(accepted["customers"]),
        "dim_product": T.build_dim_product(accepted["products"], accepted["category_translation"]),
        "dim_seller": T.build_dim_seller(accepted["sellers"]),
        "dim_date": T.build_dim_date(new_orders["purchase_ts"]),
        "fact_order_items": fact_items,
        "fact_payments": fact_pay,
    }
    return frames, new_orders


def run_pipeline(source_dir: Path = DEFAULT_SOURCE_DIR, full_refresh: bool = False,
                 engine: Engine | None = None, max_reject_ratio: float = MAX_REJECT_RATIO) -> dict:
    engine = engine or get_engine()
    source_dir = Path(source_dir)
    t0 = time.perf_counter()

    with engine.begin() as conn:
        ensure_schema(conn)
    run_id = _start_run(engine, source_dir)
    log.info("=== run %d started | source=%s | full_refresh=%s", run_id, source_dir, full_refresh)

    try:
        # ---- T2 EXTRACT
        with engine.begin() as conn:
            counts = extract_to_raw(conn, source_dir, run_id)

        # ---- T3 VALIDATE
        with engine.connect() as conn:
            frames = read_raw(conn, TABLES_FOR_TRANSFORM)
            watermark_before = None if full_refresh else get_watermark(conn, PIPELINE_NAME)
        report = run_quality_checks(frames)
        with engine.begin() as conn:
            write_quality_audit(conn, run_id, report)
        n_rejected = len(report.rejected)
        failed_checks = [r for r in report.results if not r.passed]
        log.info("Quality: %d checks, %d with failures, %d rows rejected",
                 len(report.results), len(failed_checks), n_rejected)
        enforce_reject_threshold(report, max_reject_ratio)

        # ---- TRANSFORM (pure pandas, no DB)
        log.info("Watermark before run: %s", watermark_before)
        staging, new_orders = build_staging_frames(report.accepted, watermark_before)
        log.info("Incremental: %d new orders -> %d fact rows",
                 len(new_orders), len(staging["fact_order_items"]))

        # ---- T4 LOAD + WATERMARK (atomic)
        with engine.begin() as conn:
            if full_refresh:
                reset_watermark(conn, PIPELINE_NAME)
            result = load_star_schema(conn, run_id, staging)
            watermark_after = watermark_before
            if not new_orders.empty:
                watermark_after = new_orders["purchase_ts"].max()
                set_watermark(conn, PIPELINE_NAME, watermark_after, run_id)

        # ---- T5
        summary = {
            "run_id": run_id, "status": "SUCCESS",
            "rows_extracted": sum(counts.values()), "rows_rejected": n_rejected,
            "new_orders": len(new_orders),
            "fact_inserted": result.fact_inserted, "fact_updated": result.fact_updated,
            "payments_inserted": result.payments_inserted,
            "watermark_before": watermark_before, "watermark_after": watermark_after,
            "seconds": round(time.perf_counter() - t0, 1),
        }
        _finish_run(engine, run_id, "SUCCESS",
                    watermark_before=_py(watermark_before), watermark_after=_py(watermark_after),
                    rows_extracted=summary["rows_extracted"], rows_rejected=n_rejected,
                    fact_rows_inserted=result.fact_inserted, fact_rows_updated=result.fact_updated)
        log.info("=== run %d SUCCESS in %.1fs | %s", run_id, summary["seconds"],
                 {k: summary[k] for k in ("new_orders", "fact_inserted", "fact_updated",
                                          "rows_rejected")})
        return summary

    except Exception as exc:
        log.exception("=== run %d FAILED: %s", run_id, exc)
        try:
            _finish_run(engine, run_id, "FAILED", error_message=f"{type(exc).__name__}: {exc}"[:2000])
        except Exception:  # pragma: no cover - never hide the original error
            log.exception("Could not record failure for run %d", run_id)
        raise


def _py(ts):
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).to_pydatetime()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Olist supply-chain ETL pipeline")
    ap.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    ap.add_argument("--full-refresh", action="store_true",
                    help="ignore the watermark and reprocess everything (still no duplicates)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    setup_logging(getattr(logging, args.log_level.upper()))
    try:
        run_pipeline(args.source_dir, full_refresh=args.full_refresh)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())

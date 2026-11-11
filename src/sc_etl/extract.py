"""EXTRACT: land the source CSV files in the `raw` schema, unchanged.

Every value is kept as TEXT so that nothing is lost or silently converted
at this stage. Bad values (e.g. an unparseable date) stay visible in raw and
are dealt with later by the quality checks.

Raw tables are TRUNCATE + reloaded on every run: raw always mirrors the
latest landed files, which makes this stage safe to rerun.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy.engine import Connection

from .db import copy_dataframe

log = logging.getLogger(__name__)

# table name -> (file name, expected columns): the "data contract".
SOURCES: dict[str, tuple[str, list[str]]] = {
    "orders": ("olist_orders_dataset.csv", [
        "order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date"]),
    "order_items": ("olist_order_items_dataset.csv", [
        "order_id", "order_item_id", "product_id", "seller_id",
        "shipping_limit_date", "price", "freight_value"]),
    "order_payments": ("olist_order_payments_dataset.csv", [
        "order_id", "payment_sequential", "payment_type",
        "payment_installments", "payment_value"]),
    "order_reviews": ("olist_order_reviews_dataset.csv", [
        "review_id", "order_id", "review_score", "review_comment_title",
        "review_comment_message", "review_creation_date", "review_answer_timestamp"]),
    "customers": ("olist_customers_dataset.csv", [
        "customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state"]),
    "products": ("olist_products_dataset.csv", [
        "product_id", "product_category_name", "product_name_lenght",
        "product_description_lenght", "product_photos_qty", "product_weight_g",
        "product_length_cm", "product_height_cm", "product_width_cm"]),
    "sellers": ("olist_sellers_dataset.csv", [
        "seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"]),
    "geolocation": ("olist_geolocation_dataset.csv", [
        "geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng",
        "geolocation_city", "geolocation_state"]),
    "category_translation": ("product_category_name_translation.csv", [
        "product_category_name", "product_category_name_english"]),
}

# Files that must be present. Geolocation is optional (not used by the star schema).
REQUIRED = [t for t in SOURCES if t != "geolocation"]


class SchemaMismatchError(ValueError):
    """A source file's header does not match the data contract."""


def read_source_csv(path: Path, expected_columns: list[str]) -> pd.DataFrame:
    # dtype=str keeps values exactly as in the file (e.g. zip '01037' keeps its 0).
    # Only truly empty fields become NULL. utf-8-sig strips a BOM if present.
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""],
                     encoding="utf-8-sig")
    missing = [c for c in expected_columns if c not in df.columns]
    extra = [c for c in df.columns if c not in expected_columns]
    if missing:
        raise SchemaMismatchError(f"{path.name}: missing columns {missing}")
    if extra:
        log.warning("%s: ignoring unexpected columns %s", path.name, extra)
    return df[expected_columns]


def extract_to_raw(conn: Connection, source_dir: Path, run_id: int) -> dict[str, int]:
    """Load every source file into raw.<table>. Returns row counts per table."""
    source_dir = Path(source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    counts: dict[str, int] = {}
    ingested_at = datetime.now(timezone.utc).isoformat()
    for table, (file_name, columns) in SOURCES.items():
        path = source_dir / file_name
        if not path.exists():
            if table in REQUIRED:
                raise FileNotFoundError(f"Required source file missing: {path}")
            log.info("Optional file %s not present, skipping", file_name)
            continue
        df = read_source_csv(path, columns)
        df["_source_file"] = file_name
        df["_run_id"] = run_id
        df["_ingested_at"] = ingested_at
        conn.exec_driver_sql(f"TRUNCATE raw.{table}")
        counts[table] = copy_dataframe(conn, df, f"raw.{table}")
        log.info("Extracted %-22s -> raw.%-22s %9d rows", file_name, table, counts[table])
    return counts


def read_raw(conn: Connection, tables: list[str]) -> dict[str, pd.DataFrame]:
    """Read raw tables back as all-string DataFrames (lineage columns dropped)."""
    frames = {}
    for t in tables:
        cols = ", ".join(SOURCES[t][1])
        # Columns are TEXT, so values arrive as str or None. (Passing dtype=str
        # here would turn NULLs into the literal string 'None'.)
        frames[t] = pd.read_sql(f"SELECT {cols} FROM raw.{t}", conn)
    return frames

"""VALIDATE: data-quality checks on the raw (string) data.

Each check produces a boolean "failed" mask over one table.
  * severity "error" -> failing rows are REJECTED (kept out of the warehouse
    and written to audit.rejected_records with the reason)
  * severity "warn"  -> counted and logged only; the row is still loaded

Check categories required by the project:
  null primary keys, duplicate records, invalid dates,
  broken foreign keys, invalid numerical values (+ domain checks).

Checks run parent tables first (customers, products, sellers -> orders ->
items/payments/reviews) so that a rejected parent also causes its children
to fail the foreign-key check. Nothing that references bad data gets loaded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd

log = logging.getLogger(__name__)

TS_FORMAT = "%Y-%m-%d %H:%M:%S"
MIN_VALID_TS = pd.Timestamp("2000-01-01")

ORDER_STATUSES = {"created", "approved", "invoiced", "processing", "shipped",
                  "delivered", "canceled", "unavailable"}

PRIMARY_KEYS = {
    "customers": ["customer_id"],
    "products": ["product_id"],
    "sellers": ["seller_id"],
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "order_payments": ["order_id", "payment_sequential"],
    "order_reviews": ["review_id", "order_id"],
}


class DataQualityError(RuntimeError):
    """Raised when too much of a table fails checks (circuit breaker)."""


@dataclass
class CheckResult:
    check_name: str
    table_name: str
    check_type: str
    severity: str
    rows_checked: int
    rows_failed: int

    @property
    def passed(self) -> bool:
        return self.rows_failed == 0


@dataclass
class QualityReport:
    results: list[CheckResult]
    accepted: dict[str, pd.DataFrame]
    rejected: pd.DataFrame  # columns: table_name, record_key, check_name
    totals: dict[str, int] = field(default_factory=dict)

    def rejected_count(self, table: str) -> int:
        return self.totals.get(table, 0) - len(self.accepted.get(table, []))


# ---------------------------------------------------------------- helpers
def parse_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, format=TS_FORMAT, errors="coerce")


def invalid_ts_mask(s: pd.Series, required: bool = False) -> pd.Series:
    """True where a value is present but unparseable / out of range,
    or (if required) missing."""
    parsed = parse_ts(s)
    now = pd.Timestamp.now()
    bad = (s.notna() & parsed.isna()) | (parsed < MIN_VALID_TS) | (parsed > now)
    if required:
        bad |= s.isna()
    return bad.fillna(False)


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def make_key(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    return df[cols].astype("string").fillna("<NULL>").agg("|".join, axis=1)


# ---------------------------------------------------------------- engine
class _Checker:
    def __init__(self, frames: dict[str, pd.DataFrame]):
        self.frames = frames
        self.results: list[CheckResult] = []
        self.reject = {t: pd.Series(False, index=df.index) for t, df in frames.items()}
        self.rejected_rows: list[pd.DataFrame] = []

    def accepted(self, table: str) -> pd.DataFrame:
        return self.frames[table][~self.reject[table]]

    def check(self, name: str, table: str, check_type: str, severity: str,
              mask: pd.Series) -> None:
        df = self.frames[table]
        mask = mask.reindex(df.index, fill_value=False).astype(bool)
        n_failed = int(mask.sum())
        self.results.append(CheckResult(name, table, check_type, severity, len(df), n_failed))
        level = logging.INFO if n_failed == 0 else (
            logging.WARNING if severity == "warn" else logging.ERROR)
        log.log(level, "DQ %-38s %-15s %-5s failed=%d/%d", name, table, severity,
                n_failed, len(df))
        if severity == "error" and n_failed:
            self.reject[table] |= mask
            keys = make_key(df[mask], PRIMARY_KEYS[table])
            self.rejected_rows.append(pd.DataFrame(
                {"table_name": table, "record_key": keys.values, "check_name": name}))

    # generic checks
    def null_pk(self, table: str) -> None:
        df = self.frames[table]
        self.check(f"{table}_null_pk", table, "null_pk", "error",
                   df[PRIMARY_KEYS[table]].isna().any(axis=1))

    def duplicate_pk(self, table: str) -> None:
        # keep the first occurrence, reject the extra copies
        df = self.frames[table]
        self.check(f"{table}_duplicate_pk", table, "duplicate", "error",
                   df.duplicated(subset=PRIMARY_KEYS[table], keep="first"))

    def foreign_key(self, child: str, col: str, parent: str, parent_col: str,
                    severity: str = "error") -> None:
        valid = set(self.accepted(parent)[parent_col].dropna())
        df = self.frames[child]
        self.check(f"{child}_fk_{parent}", child, "foreign_key", severity,
                   df[col].notna() & ~df[col].isin(valid))


def run_quality_checks(frames: dict[str, pd.DataFrame]) -> QualityReport:
    c = _Checker(frames)

    # ---- dimensions
    for t in ("customers", "products", "sellers"):
        c.null_pk(t)
        c.duplicate_pk(t)
    for t, col in (("customers", "customer_state"), ("sellers", "seller_state")):
        s = frames[t][col]
        c.check(f"{t}_invalid_state", t, "domain", "warn",
                ~s.fillna("").str.fullmatch(r"[A-Za-z]{2}"))
    p = frames["products"]
    c.check("products_missing_category", "products", "domain", "warn",
            p["product_category_name"].isna())
    weight = to_num(p["product_weight_g"])
    c.check("products_nonpositive_weight", "products", "invalid_number", "warn",
            weight.isna() | (weight <= 0))
    dims = [to_num(p[col]) for col in ("product_length_cm", "product_height_cm", "product_width_cm")]
    c.check("products_negative_dimension", "products", "invalid_number", "error",
            pd.concat([(d < 0) for d in dims], axis=1).any(axis=1))

    # ---- orders
    o = frames["orders"]
    c.null_pk("orders")
    c.duplicate_pk("orders")
    c.check("orders_invalid_purchase_ts", "orders", "invalid_date", "error",
            invalid_ts_mask(o["order_purchase_timestamp"], required=True))
    other_ts = ["order_approved_at", "order_delivered_carrier_date",
                "order_delivered_customer_date", "order_estimated_delivery_date"]
    c.check("orders_unparseable_ts", "orders", "invalid_date", "error",
            pd.concat([invalid_ts_mask(o[col]) for col in other_ts], axis=1).any(axis=1))
    purchase = parse_ts(o["order_purchase_timestamp"])
    delivered = parse_ts(o["order_delivered_customer_date"])
    c.check("orders_delivered_before_purchase", "orders", "invalid_date", "error",
            (delivered < purchase).fillna(False))
    c.check("orders_approved_before_purchase", "orders", "invalid_date", "warn",
            (parse_ts(o["order_approved_at"]) < purchase).fillna(False))
    c.check("orders_carrier_before_purchase", "orders", "invalid_date", "warn",
            (parse_ts(o["order_delivered_carrier_date"]) < purchase).fillna(False))
    c.check("orders_unknown_status", "orders", "domain", "warn",
            ~o["order_status"].isin(ORDER_STATUSES))
    c.check("orders_delivered_missing_date", "orders", "domain", "warn",
            (o["order_status"] == "delivered") & o["order_delivered_customer_date"].isna())
    c.foreign_key("orders", "customer_id", "customers", "customer_id")

    # ---- order items
    i = frames["order_items"]
    c.null_pk("order_items")
    c.duplicate_pk("order_items")
    item_no = to_num(i["order_item_id"])
    c.check("order_items_invalid_item_id", "order_items", "invalid_number", "error",
            item_no.isna() | (item_no < 1) | (item_no % 1 != 0))
    price, freight = to_num(i["price"]), to_num(i["freight_value"])
    c.check("order_items_invalid_price", "order_items", "invalid_number", "error",
            price.isna() | (price <= 0))
    c.check("order_items_invalid_freight", "order_items", "invalid_number", "error",
            freight.isna() | (freight < 0))
    c.check("order_items_invalid_shipping_limit", "order_items", "invalid_date", "error",
            invalid_ts_mask(i["shipping_limit_date"]))
    c.foreign_key("order_items", "order_id", "orders", "order_id")
    c.foreign_key("order_items", "product_id", "products", "product_id")
    c.foreign_key("order_items", "seller_id", "sellers", "seller_id")

    # ---- payments
    pay = frames["order_payments"]
    c.null_pk("order_payments")
    c.duplicate_pk("order_payments")
    value = to_num(pay["payment_value"])
    c.check("order_payments_invalid_value", "order_payments", "invalid_number", "error",
            value.isna() | (value < 0))
    inst = to_num(pay["payment_installments"])
    c.check("order_payments_invalid_installments", "order_payments", "invalid_number", "warn",
            inst.isna() | (inst < 1))
    c.foreign_key("order_payments", "order_id", "orders", "order_id")

    # ---- reviews
    r = frames["order_reviews"]
    c.null_pk("order_reviews")
    c.duplicate_pk("order_reviews")
    score = to_num(r["review_score"])
    c.check("order_reviews_invalid_score", "order_reviews", "invalid_number", "error",
            ~score.isin([1, 2, 3, 4, 5]))
    c.foreign_key("order_reviews", "order_id", "orders", "order_id")

    accepted = {t: c.accepted(t) for t in frames}
    rejected = (pd.concat(c.rejected_rows, ignore_index=True) if c.rejected_rows
                else pd.DataFrame(columns=["table_name", "record_key", "check_name"]))
    totals = {t: len(df) for t, df in frames.items()}
    return QualityReport(c.results, accepted, rejected, totals)


def enforce_reject_threshold(report: QualityReport, max_ratio: float) -> None:
    """Circuit breaker: abort the run if a table is mostly bad data. A sudden
    spike of rejects usually means an upstream bug, not genuinely bad rows."""
    for table, total in report.totals.items():
        if total == 0:
            continue
        ratio = report.rejected_count(table) / total
        if ratio > max_ratio:
            raise DataQualityError(
                f"{table}: {ratio:.1%} of rows rejected (limit {max_ratio:.1%}); aborting load")

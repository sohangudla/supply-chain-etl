"""TRANSFORM: clean the accepted rows and shape them into the star schema.

All functions here are pure (DataFrame in -> DataFrame out, no database),
which keeps them easy to unit-test.
"""
from __future__ import annotations

import pandas as pd

from .quality import parse_ts, to_num

ORDER_TS_COLS = {
    "order_purchase_timestamp": "purchase_ts",
    "order_approved_at": "approved_ts",
    "order_delivered_carrier_date": "delivered_carrier_ts",
    "order_delivered_customer_date": "delivered_customer_ts",
    "order_estimated_delivery_date": "estimated_delivery_ts",
}


def _clean_city(s: pd.Series) -> pd.Series:
    return s.str.strip().str.lower().str.replace(r"\s+", " ", regex=True)


def _clean_zip(s: pd.Series) -> pd.Series:
    # zip prefixes are 5 digits; a leading zero lost by a spreadsheet tool would
    # turn '01037' into '1037', so pad defensively.
    return s.str.strip().str.zfill(5)


def date_key(ts: pd.Series) -> pd.Series:
    """Timestamp -> integer YYYYMMDD (the dim_date primary key)."""
    return (ts.dt.year * 10000 + ts.dt.month * 100 + ts.dt.day).astype("Int64")


# ---------------------------------------------------------------- dimensions
def build_dim_customer(customers: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "customer_id": customers["customer_id"].str.strip(),
        "customer_unique_id": customers["customer_unique_id"].str.strip(),
        "zip_code_prefix": _clean_zip(customers["customer_zip_code_prefix"]),
        "city": _clean_city(customers["customer_city"]),
        "state": customers["customer_state"].str.strip().str.upper(),
    })


def build_dim_seller(sellers: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "seller_id": sellers["seller_id"].str.strip(),
        "zip_code_prefix": _clean_zip(sellers["seller_zip_code_prefix"]),
        "city": _clean_city(sellers["seller_city"]),
        "state": sellers["seller_state"].str.strip().str.upper(),
    })


def build_dim_product(products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    mapping = dict(zip(translation["product_category_name"].str.strip(),
                       translation["product_category_name_english"].str.strip()))
    pt = products["product_category_name"].str.strip()
    # translated name -> else the Portuguese name -> else 'unknown'
    en = pt.map(mapping).fillna(pt).fillna("unknown")
    return pd.DataFrame({
        "product_id": products["product_id"].str.strip(),
        "category_name_pt": pt,
        "category_name_en": en,
        "weight_g": to_num(products["product_weight_g"]),
        "length_cm": to_num(products["product_length_cm"]),
        "height_cm": to_num(products["product_height_cm"]),
        "width_cm": to_num(products["product_width_cm"]),
        "photos_qty": to_num(products["product_photos_qty"]).astype("Int64"),
    })


def build_dim_date(timestamps: pd.Series) -> pd.DataFrame:
    """One row per calendar day between the min and max date seen."""
    ts = timestamps.dropna()
    if ts.empty:
        return pd.DataFrame(columns=["date_key", "full_date", "year", "quarter", "month",
                                     "month_name", "year_month", "day_of_month",
                                     "day_of_week", "day_name", "is_weekend"])
    days = pd.Series(pd.date_range(ts.min().normalize(), ts.max().normalize(), freq="D"))
    return pd.DataFrame({
        "date_key": date_key(days),
        "full_date": days.dt.date,
        "year": days.dt.year,
        "quarter": days.dt.quarter,
        "month": days.dt.month,
        "month_name": days.dt.month_name(),
        "year_month": days.dt.strftime("%Y-%m"),
        "day_of_month": days.dt.day,
        "day_of_week": days.dt.dayofweek + 1,
        "day_name": days.dt.day_name(),
        "is_weekend": days.dt.dayofweek >= 5,
    })


# ---------------------------------------------------------------- facts
def clean_orders(orders: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({
        "order_id": orders["order_id"].str.strip(),
        "customer_id": orders["customer_id"].str.strip(),
        "order_status": orders["order_status"].str.strip().str.lower(),
    })
    for src, dst in ORDER_TS_COLS.items():
        out[dst] = parse_ts(orders[src])
    return out


def filter_incremental(orders: pd.DataFrame, watermark: pd.Timestamp | None) -> pd.DataFrame:
    """Keep only orders purchased strictly after the watermark."""
    if watermark is None or pd.isna(watermark):
        return orders
    return orders[orders["purchase_ts"] > watermark]


def order_review_scores(reviews: pd.DataFrame) -> pd.Series:
    """Average review score per order (an order can have several reviews)."""
    score = to_num(reviews["review_score"])
    return score.groupby(reviews["order_id"].str.strip()).mean().round(2)


def build_fact_order_items(orders: pd.DataFrame, items: pd.DataFrame,
                           reviews: pd.DataFrame) -> pd.DataFrame:
    """orders: output of clean_orders (already incremental-filtered)."""
    it = pd.DataFrame({
        "order_id": items["order_id"].str.strip(),
        "order_item_id": to_num(items["order_item_id"]).astype("Int64"),
        "product_id": items["product_id"].str.strip(),
        "seller_id": items["seller_id"].str.strip(),
        "shipping_limit_ts": parse_ts(items["shipping_limit_date"]),
        "price": to_num(items["price"]).round(2),
        "freight_value": to_num(items["freight_value"]).round(2),
    })
    # inner join: only items of orders in this (incremental) batch
    f = it.merge(orders, on="order_id", how="inner", validate="many_to_one")

    f["item_total"] = (f["price"] + f["freight_value"]).round(2)
    f["purchase_date_key"] = date_key(f["purchase_ts"])
    delivered = f["delivered_customer_ts"]
    f["is_delivered"] = (f["order_status"] == "delivered") & delivered.notna()
    f["delivery_days"] = ((delivered - f["purchase_ts"]).dt.total_seconds() / 86400).round(2)
    # Late = delivered on a later calendar day than the estimated date.
    # (estimated dates are given at 00:00, so comparing dates is the fair test)
    days_late = (delivered.dt.normalize() - f["estimated_delivery_ts"].dt.normalize()).dt.days
    f["days_late"] = days_late.where(f["is_delivered"]).astype("Int64")
    f["is_late"] = (f["days_late"] > 0).astype("boolean").where(f["is_delivered"], pd.NA)
    f["order_review_score"] = f["order_id"].map(order_review_scores(reviews))

    cols = ["order_id", "order_item_id", "customer_id", "product_id", "seller_id",
            "purchase_date_key", "order_status", "purchase_ts", "approved_ts",
            "delivered_carrier_ts", "delivered_customer_ts", "estimated_delivery_ts",
            "shipping_limit_ts", "price", "freight_value", "item_total", "delivery_days",
            "is_delivered", "is_late", "days_late", "order_review_score"]
    return f[cols].reset_index(drop=True)


def build_fact_payments(orders: pd.DataFrame, payments: pd.DataFrame) -> pd.DataFrame:
    p = pd.DataFrame({
        "order_id": payments["order_id"].str.strip(),
        "payment_sequential": to_num(payments["payment_sequential"]).astype("Int64"),
        "payment_type": payments["payment_type"].str.strip().str.lower(),
        "installments": to_num(payments["payment_installments"]).astype("Int64"),
        "payment_value": to_num(payments["payment_value"]).round(2),
    })
    f = p.merge(orders[["order_id", "customer_id", "purchase_ts"]], on="order_id", how="inner")
    f["purchase_date_key"] = date_key(f["purchase_ts"])
    return f[["order_id", "payment_sequential", "customer_id", "purchase_date_key",
              "payment_type", "installments", "payment_value"]].reset_index(drop=True)

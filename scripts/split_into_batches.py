"""Simulate data arriving over time.

Olist is a single historical snapshot. To exercise incremental loading we
split it by order_purchase_timestamp into landing batches, as if the source
system exported new orders every few months:

  batch_01: orders purchased  <= 2017-06-30
  batch_02: 2017-06-30 < ts   <= 2017-12-31
  batch_03: 2017-12-31 < ts          (rest)

Order-level files (orders, items, payments, reviews) are split by order;
reference files (customers, products, sellers, translation) are copied in
full to each batch, like a daily full export of master data.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ORDER_FILES = ["olist_order_items_dataset.csv", "olist_order_payments_dataset.csv",
               "olist_order_reviews_dataset.csv"]
REFERENCE_FILES = ["olist_customers_dataset.csv", "olist_products_dataset.csv",
                   "olist_sellers_dataset.csv", "product_category_name_translation.csv"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=ROOT / "data" / "source")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "landing")
    ap.add_argument("--cutoffs", nargs="+", default=["2017-06-30 23:59:59", "2017-12-31 23:59:59"])
    args = ap.parse_args()

    read = lambda f: pd.read_csv(args.source / f, dtype=str, keep_default_na=False,
                                 na_values=[""], encoding="utf-8-sig")
    orders = read("olist_orders_dataset.csv")
    ts = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")
    bounds = [pd.Timestamp.min] + [pd.Timestamp(c) for c in args.cutoffs] + [pd.Timestamp.max]
    children = {f: read(f) for f in ORDER_FILES}

    for n, (lo, hi) in enumerate(zip(bounds[:-1], bounds[1:]), start=1):
        out = args.out / f"batch_{n:02d}"
        out.mkdir(parents=True, exist_ok=True)
        sel = orders[(ts > lo) & (ts <= hi)]
        ids = set(sel["order_id"])
        sel.to_csv(out / "olist_orders_dataset.csv", index=False)
        for f, df in children.items():
            df[df["order_id"].isin(ids)].to_csv(out / f, index=False)
        for f in REFERENCE_FILES:
            shutil.copy2(args.source / f, out / f)
        print(f"{out.name}: {len(sel):6d} orders  ({lo if n > 1 else 'start'} -> {hi if n < len(bounds) - 1 else 'end'})")
    unassigned = ts.isna().sum()
    if unassigned:
        print(f"WARNING: {unassigned} orders with unparseable purchase date not assigned to any batch")


if __name__ == "__main__":
    main()

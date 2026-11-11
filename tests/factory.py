"""Builds small, fully-controlled Olist-shaped datasets for tests.

All values are strings, exactly as the pipeline sees them after extraction.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from sc_etl.extract import SOURCES

FMT = "%Y-%m-%d %H:%M:%S"


def make_dataset(n_orders: int = 20, start: str = "2018-01-01 10:00:00",
                 id_prefix: str = "o") -> dict[str, pd.DataFrame]:
    t0 = pd.Timestamp(start)
    customers, orders, items, payments, reviews = [], [], [], [], []
    for i in range(n_orders):
        oid, cid = f"{id_prefix}{i:04d}", f"c{id_prefix}{i:04d}"
        purchase = t0 + pd.Timedelta(days=i)
        late = i % 4 == 0                       # every 4th order is late
        delivered = purchase + pd.Timedelta(days=12 if late else 5)
        estimated = (purchase + pd.Timedelta(days=10)).normalize()
        customers.append([cid, f"u{i}", f"{1000 + i:05d}", " Sao  Paulo ", "sp"])
        orders.append([oid, cid, "delivered", purchase.strftime(FMT),
                       (purchase + pd.Timedelta(hours=1)).strftime(FMT),
                       (purchase + pd.Timedelta(days=1)).strftime(FMT),
                       delivered.strftime(FMT), estimated.strftime(FMT)])
        n_items = 2 if i % 3 == 0 else 1
        total = 0.0
        for k in range(1, n_items + 1):
            price = 10.0 + i
            total += price + 5.0
            items.append([oid, str(k), f"p{i % 5}", f"s{i % 3}",
                          (purchase + pd.Timedelta(days=2)).strftime(FMT), f"{price:.2f}", "5.00"])
        payments.append([oid, "1", "credit_card", "1", f"{total:.2f}"])
        reviews.append([f"r{id_prefix}{i:04d}", oid, str(i % 5 + 1), None, None,
                        delivered.strftime(FMT), delivered.strftime(FMT)])

    cols = {t: c for t, (_, c) in SOURCES.items()}
    products = [[f"p{j}", cat, "40", "300", "1", "500", "20", "10", "15"]
                for j, cat in enumerate(["perfumaria", "esporte_lazer", "pet_shop", None, "brinquedos"])]
    return {
        "customers": pd.DataFrame(customers, columns=cols["customers"]),
        "orders": pd.DataFrame(orders, columns=cols["orders"]),
        "order_items": pd.DataFrame(items, columns=cols["order_items"]),
        "order_payments": pd.DataFrame(payments, columns=cols["order_payments"]),
        "order_reviews": pd.DataFrame(reviews, columns=cols["order_reviews"]),
        "products": pd.DataFrame(products, columns=cols["products"]),
        "sellers": pd.DataFrame([[f"s{j}", "13023", "campinas", "SP"] for j in range(3)],
                                columns=cols["sellers"]),
        "category_translation": pd.DataFrame(
            [["perfumaria", "perfumery"], ["esporte_lazer", "sports_leisure"],
             ["brinquedos", "toys"]], columns=cols["category_translation"]),
    }


def write_dataset(ds: dict[str, pd.DataFrame], directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for table, df in ds.items():
        df.to_csv(directory / SOURCES[table][0], index=False)
    return directory


def inject_faults(ds: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Inject one of each fault type into a copy of the dataset.
    Expected rejections are documented next to each injection."""
    ds = {k: v.copy() for k, v in ds.items()}
    o, it = ds["orders"], ds["order_items"]
    o.loc[1, "order_id"] = None                                   # orders_null_pk
    o.loc[2, "order_purchase_timestamp"] = "2018-13-45 10:00:00"  # orders_invalid_purchase_ts
    o.loc[3, "order_delivered_customer_date"] = "2017-01-01 00:00:00"  # delivered_before_purchase
    o.loc[5, "customer_id"] = "missing_customer"                   # orders_fk_customers
    ds["orders"] = pd.concat([o, o.iloc[[6]]], ignore_index=True)  # orders_duplicate_pk
    it.loc[it.index[-1], "price"] = "-3.00"                        # invalid_price (negative)
    it.loc[it.index[-2], "price"] = "abc"                          # invalid_price (non-numeric)
    it.loc[it.index[-3], "product_id"] = "missing_product"         # fk_products
    orphan = it.iloc[[0]].copy()
    orphan["order_id"] = "ghost_order"                             # fk_orders (orphan item)
    ds["order_items"] = pd.concat([it, orphan], ignore_index=True)
    ds["order_reviews"].loc[0, "review_score"] = "7"               # invalid_score
    return ds

"""Quick recheck: warehouse totals vs the source CSV.
    python scripts/verify_warehouse.py"""
import pandas as pd
from sqlalchemy import text

from sc_etl.config import PROJECT_ROOT
from sc_etl.db import get_engine

with get_engine().connect() as c:
    rows = c.execute(text("SELECT COUNT(*) FROM warehouse.fact_order_items")).scalar()
    revenue = c.execute(text("SELECT SUM(price) FROM warehouse.fact_order_items")).scalar()
    dupes = c.execute(text("""SELECT COUNT(*) FROM (SELECT order_id, order_item_id
        FROM warehouse.fact_order_items GROUP BY 1, 2 HAVING COUNT(*) > 1) d""")).scalar()

src = pd.read_csv(PROJECT_ROOT / "data" / "source" / "olist_order_items_dataset.csv")
print(f"fact rows      : {rows:,}   (source CSV: {len(src):,})")
print(f"revenue        : {revenue:,.2f}   (source CSV: {src.price.sum():,.2f})")
print(f"duplicate keys : {dupes}")
print("RESULT:", "MATCH" if rows == len(src) and round(float(revenue), 2) == round(src.price.sum(), 2)
      and dupes == 0 else "MISMATCH")

import pandas as pd
import pytest

from sc_etl import transform as T
from tests.factory import make_dataset


@pytest.fixture
def ds():
    return make_dataset(n_orders=12)


def test_date_key():
    s = pd.Series(pd.to_datetime(["2018-03-07 23:59:59", "2016-12-31 00:00:00"]))
    assert T.date_key(s).tolist() == [20180307, 20161231]


def test_dim_customer_normalises_text(ds):
    dim = T.build_dim_customer(ds["customers"])
    assert dim.loc[0, "city"] == "sao paulo"      # trimmed, lower-cased, single spaces
    assert dim.loc[0, "state"] == "SP"
    assert dim.loc[0, "zip_code_prefix"] == "01000"


def test_zip_padding_restores_leading_zero():
    df = pd.DataFrame({"seller_id": ["s"], "seller_zip_code_prefix": ["1037"],
                       "seller_city": ["x"], "seller_state": ["sp"]})
    assert T.build_dim_seller(df).loc[0, "zip_code_prefix"] == "01037"


def test_dim_product_category_translation_fallbacks(ds):
    dim = T.build_dim_product(ds["products"], ds["category_translation"]).set_index("product_id")
    assert dim.loc["p0", "category_name_en"] == "perfumery"   # translated
    assert dim.loc["p2", "category_name_en"] == "pet_shop"    # no translation -> keep pt name
    assert dim.loc["p3", "category_name_en"] == "unknown"     # missing category


def test_dim_date_is_continuous():
    ts = pd.Series(pd.to_datetime(["2018-01-30 10:00", "2018-02-02 08:00"]))
    d = T.build_dim_date(ts)
    assert d["date_key"].tolist() == [20180130, 20180131, 20180201, 20180202]
    assert d.loc[d.date_key == 20180203].empty
    assert bool(d.loc[d.date_key == 20180201, "is_weekend"].iloc[0]) is False  # Thursday
    assert d.loc[d.date_key == 20180201, "day_of_week"].iloc[0] == 4
    assert d["year_month"].iloc[-1] == "2018-02"


def test_filter_incremental_is_strictly_greater(ds):
    orders = T.clean_orders(ds["orders"])
    wm = orders["purchase_ts"].iloc[4]
    out = T.filter_incremental(orders, wm)
    assert len(out) == len(orders) - 5          # the watermark row itself is excluded
    assert (out["purchase_ts"] > wm).all()
    assert len(T.filter_incremental(orders, None)) == len(orders)


def test_fact_metrics(ds):
    orders = T.clean_orders(ds["orders"])
    fact = T.build_fact_order_items(orders, ds["order_items"], ds["order_reviews"])
    assert len(fact) == len(ds["order_items"])
    first = fact[fact.order_id == "o0000"].iloc[0]           # order 0 is late (12 vs 10 days)
    assert first["is_late"] == True and first["days_late"] == 2
    assert first["delivery_days"] == 12.0
    assert first["item_total"] == first["price"] + first["freight_value"]
    on_time = fact[fact.order_id == "o0001"].iloc[0]
    assert on_time["is_late"] == False and on_time["days_late"] == -5
    assert fact["purchase_date_key"].iloc[0] == 20180101


def test_undelivered_order_has_null_lateness(ds):
    o = ds["orders"].copy()
    o.loc[0, "order_status"] = "shipped"
    o.loc[0, "order_delivered_customer_date"] = None
    fact = T.build_fact_order_items(T.clean_orders(o), ds["order_items"], ds["order_reviews"])
    row = fact[fact.order_id == "o0000"].iloc[0]
    assert row["is_delivered"] == False
    assert pd.isna(row["is_late"]) and pd.isna(row["days_late"]) and pd.isna(row["delivery_days"])


def test_review_score_is_averaged_per_order():
    r = pd.DataFrame({"order_id": ["a", "a", "b"], "review_score": ["5", "2", "4"]})
    assert T.order_review_scores(r).to_dict() == {"a": 3.5, "b": 4.0}


def test_payments_only_for_batch_orders(ds):
    orders = T.clean_orders(ds["orders"]).iloc[:3]
    pay = T.build_fact_payments(orders, ds["order_payments"])
    assert sorted(pay.order_id) == ["o0000", "o0001", "o0002"]
    assert pay["customer_id"].notna().all()

import pandas as pd
import pytest

from sc_etl.quality import (DataQualityError, enforce_reject_threshold, invalid_ts_mask,
                            run_quality_checks)
from tests.factory import inject_faults, make_dataset


def failed(report, name):
    return next(r for r in report.results if r.check_name == name).rows_failed


def test_clean_dataset_has_no_rejects():
    report = run_quality_checks(make_dataset(20))
    assert report.rejected.empty
    errors = [r for r in report.results if r.severity == "error" and not r.passed]
    assert errors == []


@pytest.fixture(scope="module")
def dirty_report():
    return run_quality_checks(inject_faults(make_dataset(20)))


@pytest.mark.parametrize("check,expected", [
    ("orders_null_pk", 1),
    ("orders_duplicate_pk", 1),
    ("orders_invalid_purchase_ts", 1),
    ("orders_delivered_before_purchase", 1),
    ("orders_fk_customers", 1),
    ("order_items_invalid_price", 2),          # negative + non-numeric
    ("order_items_fk_products", 1),
    ("order_reviews_invalid_score", 1),
])
def test_each_injected_fault_is_detected(dirty_report, check, expected):
    assert failed(dirty_report, check) == expected


def test_rejected_orders_cascade_to_items(dirty_report):
    # orders 1(null pk -> its items cannot match), 2, 3, 5 are rejected; their items
    # plus the orphan 'ghost_order' item must fail the FK check.
    rejected_orders = set(dirty_report.rejected.query("table_name == 'orders'").record_key)
    assert {"o0002", "o0003", "o0005"} <= rejected_orders
    fk = failed(dirty_report, "order_items_fk_orders")
    assert fk >= 4  # o0001,o0002,o0003,o0005 have >=1 item each, + ghost
    accepted_items = dirty_report.accepted["order_items"]
    assert not accepted_items["order_id"].isin(["o0002", "o0003", "o0005", "ghost_order"]).any()


def test_duplicate_keeps_first_copy(dirty_report):
    accepted = dirty_report.accepted["orders"]
    assert (accepted["order_id"] == "o0006").sum() == 1


def test_invalid_ts_mask_flags_unparseable_and_future():
    s = pd.Series(["2018-01-01 10:00:00", "not a date", None, "2999-01-01 00:00:00", "1990-01-01 00:00:00"])
    assert invalid_ts_mask(s).tolist() == [False, True, False, True, True]
    assert invalid_ts_mask(s, required=True).tolist() == [False, True, True, True, True]


def test_circuit_breaker_aborts_on_mass_rejects():
    ds = make_dataset(20)
    ds["order_items"]["price"] = "-1"          # every item invalid
    report = run_quality_checks(ds)
    with pytest.raises(DataQualityError, match="order_items"):
        enforce_reject_threshold(report, max_ratio=0.05)


def test_warn_checks_do_not_reject():
    ds = make_dataset(10)
    ds["products"].loc[0, "product_weight_g"] = "0"
    report = run_quality_checks(ds)
    assert failed(report, "products_nonpositive_weight") == 1
    assert len(report.accepted["products"]) == len(ds["products"])

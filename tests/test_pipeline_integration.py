"""End-to-end tests against a real PostgreSQL database (olist_test)."""
import pandas as pd
import pytest

from sc_etl import pipeline as P
from tests.conftest import count
from tests.factory import inject_faults, make_dataset, write_dataset

pytestmark = pytest.mark.integration

FACTS = "SELECT COUNT(*) FROM warehouse.fact_order_items"
WM = "SELECT watermark_value FROM audit.etl_watermark"


def test_full_load_then_rerun_is_idempotent(pg_engine, tmp_path):
    ds = make_dataset(20)
    src = write_dataset(ds, tmp_path / "b1")

    s1 = P.run_pipeline(src, engine=pg_engine)
    assert s1["fact_inserted"] == len(ds["order_items"]) == count(pg_engine, FACTS)
    assert count(pg_engine, "SELECT COUNT(*) FROM warehouse.fact_payments") == 20

    s2 = P.run_pipeline(src, engine=pg_engine)                 # same files again
    assert s2["new_orders"] == 0 and s2["fact_inserted"] == 0
    assert count(pg_engine, FACTS) == len(ds["order_items"])

    s3 = P.run_pipeline(src, engine=pg_engine, full_refresh=True)  # ignore watermark
    assert s3["fact_inserted"] == 0 and s3["fact_updated"] == len(ds["order_items"])
    assert count(pg_engine, FACTS) == len(ds["order_items"])
    assert count(pg_engine, """SELECT COUNT(*) FROM (SELECT order_id, order_item_id
        FROM warehouse.fact_order_items GROUP BY 1, 2 HAVING COUNT(*) > 1) d""") == 0


def test_incremental_loads_only_newer_orders(pg_engine, tmp_path):
    ds = make_dataset(30)
    o = ds["orders"]
    early_ids = set(o.order_id[:10])
    batch1 = dict(ds, orders=o.iloc[:10], **{
        t: ds[t][ds[t].order_id.isin(early_ids)]
        for t in ("order_items", "order_payments", "order_reviews")})
    P.run_pipeline(write_dataset(batch1, tmp_path / "b1"), engine=pg_engine)
    wm1 = count(pg_engine, WM)
    assert pd.Timestamp(wm1) == pd.Timestamp(o.order_purchase_timestamp.iloc[9])

    # batch 2 overlaps batch 1 (re-sent old orders) + 20 new ones
    s2 = P.run_pipeline(write_dataset(ds, tmp_path / "b2"), engine=pg_engine)
    assert s2["new_orders"] == 20
    assert count(pg_engine, FACTS) == len(ds["order_items"])
    assert pd.Timestamp(count(pg_engine, WM)) == pd.Timestamp(o.order_purchase_timestamp.iloc[-1])


def test_dirty_data_is_rejected_and_audited(pg_engine, tmp_path):
    dirty = inject_faults(make_dataset(20))
    s = P.run_pipeline(write_dataset(dirty, tmp_path / "dirty"), engine=pg_engine,
                       max_reject_ratio=0.5)
    assert s["rows_rejected"] > 0
    # nothing that failed an error check reached the warehouse
    for bad in ("o0002", "o0003", "o0005", "ghost_order"):
        assert count(pg_engine, f"SELECT COUNT(*) FROM warehouse.fact_order_items WHERE order_id = '{bad}'") == 0
    assert count(pg_engine, "SELECT COUNT(*) FROM warehouse.fact_order_items WHERE price <= 0") == 0
    assert count(pg_engine, "SELECT COUNT(*) FROM audit.rejected_records") == s["rows_rejected"]
    assert count(pg_engine, "SELECT COUNT(*) FROM audit.dq_check_results WHERE NOT passed AND severity='error'") >= 8


def test_missing_source_file_marks_run_failed(pg_engine, tmp_path):
    src = write_dataset(make_dataset(5), tmp_path / "b")
    (src / "olist_orders_dataset.csv").unlink()
    with pytest.raises(FileNotFoundError):
        P.run_pipeline(src, engine=pg_engine)
    assert count(pg_engine, "SELECT status FROM audit.pipeline_runs") == "FAILED"
    assert "olist_orders_dataset.csv" in count(pg_engine, "SELECT error_message FROM audit.pipeline_runs")


def test_failure_during_load_rolls_back_facts_and_watermark(pg_engine, tmp_path, monkeypatch):
    src = write_dataset(make_dataset(10), tmp_path / "b")

    def boom(*a, **k):
        raise RuntimeError("simulated crash after facts were written")
    monkeypatch.setattr(P, "set_watermark", boom)   # fails AFTER the fact upsert ran
    with pytest.raises(RuntimeError):
        P.run_pipeline(src, engine=pg_engine)
    assert count(pg_engine, FACTS) == 0              # fact insert was rolled back
    assert count(pg_engine, "SELECT COUNT(*) FROM audit.etl_watermark") == 0

    monkeypatch.undo()                                # retry succeeds, no duplicates
    P.run_pipeline(src, engine=pg_engine)
    assert count(pg_engine, FACTS) == len(make_dataset(10)["order_items"])


def test_circuit_breaker_stops_load(pg_engine, tmp_path):
    ds = make_dataset(10)
    ds["order_items"]["price"] = "-1"
    with pytest.raises(Exception, match="rejected"):
        P.run_pipeline(write_dataset(ds, tmp_path / "b"), engine=pg_engine)
    assert count(pg_engine, FACTS) == 0
    # DQ evidence is still kept for investigation
    assert count(pg_engine, "SELECT rows_failed FROM audit.dq_check_results WHERE check_name='order_items_invalid_price'") == len(ds["order_items"])

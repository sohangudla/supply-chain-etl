import pytest

from sc_etl.extract import SchemaMismatchError, read_source_csv


def test_keeps_leading_zeros_and_empty_as_null(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text('seller_id,seller_zip_code_prefix,seller_city,seller_state\n"a","01037",,SP\n')
    df = read_source_csv(p, ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"])
    assert df.loc[0, "seller_zip_code_prefix"] == "01037"
    assert df["seller_city"].isna().all()


def test_strips_utf8_bom(tmp_path):
    p = tmp_path / "t.csv"
    p.write_bytes("﻿a,b\n1,2\n".encode("utf-8"))
    assert list(read_source_csv(p, ["a", "b"]).columns) == ["a", "b"]


def test_missing_column_raises(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("a\n1\n")
    with pytest.raises(SchemaMismatchError, match="missing columns"):
        read_source_csv(p, ["a", "b"])


def test_multiline_quoted_text_is_one_row(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text('id,msg\n1,"line one\nline two"\n2,ok\n')
    assert len(read_source_csv(p, ["id", "msg"])) == 2

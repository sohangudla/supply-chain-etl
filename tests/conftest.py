import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # so `from tests.factory import ...` works


@pytest.fixture
def pg_engine():
    """Fresh, empty olist_test database for each integration test.
    Skips (not fails) when PostgreSQL is unreachable."""
    from sc_etl.db import get_engine
    engine = get_engine(database=os.getenv("PGTEST_DATABASE", "olist_test"))
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS raw, staging, warehouse, audit CASCADE"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"PostgreSQL test database unavailable: {exc}")
    yield engine
    engine.dispose()


def count(engine, sql):
    with engine.connect() as c:
        return c.execute(text(sql)).scalar()

"""Run every query in sql/analytics/, save each result as CSV and build a
Markdown report (sample_output/analytics_report.md)."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from sc_etl.config import PROJECT_ROOT, SQL_DIR
from sc_etl.db import get_engine
from sc_etl.log import setup_logging

OUT = PROJECT_ROOT / "sample_output"
log = logging.getLogger("analytics")


def to_markdown(df: pd.DataFrame, max_rows: int = 25) -> str:
    df = df.head(max_rows).astype(object).where(df.head(max_rows).notna(), "")
    header = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "|" + "|".join("---" for _ in df.columns) + "|"
    rows = ["| " + " | ".join(map(str, r)) + " |" for r in df.itertuples(index=False)]
    return "\n".join([header, sep, *rows])


def main() -> None:
    setup_logging()
    (OUT / "analytics").mkdir(parents=True, exist_ok=True)
    engine = get_engine()
    sections = ["# Analytics results\n",
                f"Generated {pd.Timestamp.now():%Y-%m-%d %H:%M} from the `olist_dw` warehouse.\n"]
    for path in sorted((SQL_DIR / "analytics").glob("*.sql")):
        t0 = time.perf_counter()
        with engine.connect() as conn:
            # text() escapes '%' (used in comments) which psycopg2 would
            # otherwise read as a parameter placeholder
            df = pd.read_sql(text(path.read_text(encoding="utf-8")), conn)
        ms = (time.perf_counter() - t0) * 1000
        df.to_csv(OUT / "analytics" / f"{path.stem}.csv", index=False)
        log.info("%-45s %4d rows  %6.0f ms", path.name, len(df), ms)
        title = path.stem[3:].replace("_", " ").capitalize()
        sections += [f"\n## {title}\n", f"`sql/analytics/{path.name}` - {len(df)} rows, {ms:.0f} ms\n",
                     to_markdown(df), ""]
    (OUT / "analytics_report.md").write_text("\n".join(sections), encoding="utf-8")
    log.info("Report written to %s", OUT / "analytics_report.md")


if __name__ == "__main__":
    main()

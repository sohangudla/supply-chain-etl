"""Central configuration.

All secrets (database password) come from environment variables or a local
`.env` file that is git-ignored. Nothing secret is hard-coded or logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

SQL_DIR = PROJECT_ROOT / "sql"
LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_SOURCE_DIR = PROJECT_ROOT / "data" / "source"

PIPELINE_NAME = "olist_order_items"


@dataclass(frozen=True)
class DBConfig:
    host: str = field(default_factory=lambda: os.getenv("PGHOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("PGPORT", "5432")))
    database: str = field(default_factory=lambda: os.getenv("PGDATABASE", "olist_dw"))
    user: str = field(default_factory=lambda: os.getenv("PGUSER", "etl_user"))
    password: str = field(default_factory=lambda: os.getenv("PGPASSWORD", ""), repr=False)

    def url(self, database: str | None = None) -> URL:
        # URL.create escapes special characters in the password safely.
        return URL.create(
            "postgresql+psycopg2",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=database or self.database,
        )


# Circuit breaker: if more than this share of a table's rows fail an
# "error"-severity check, the run is aborted instead of loading bad data.
MAX_REJECT_RATIO = float(os.getenv("MAX_REJECT_RATIO", "0.05"))

"""Logging setup: console + rotating file in logs/pipeline.log."""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import LOG_DIR

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if any(getattr(h, "_sc_etl", False) for h in root.handlers):
        return  # already configured (e.g. called twice in tests)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    file_handler = RotatingFileHandler(
        LOG_DIR / "pipeline.log", maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    for h in (console, file_handler):
        h._sc_etl = True  # type: ignore[attr-defined]
        root.addHandler(h)
    root.setLevel(level)

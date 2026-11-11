-- Audit / control tables
CREATE TABLE IF NOT EXISTS audit.pipeline_runs (
    run_id          BIGSERIAL PRIMARY KEY,
    pipeline_name   TEXT        NOT NULL,
    source_dir      TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    status          TEXT        NOT NULL DEFAULT 'RUNNING'
                    CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED')),
    watermark_before TIMESTAMP,
    watermark_after  TIMESTAMP,
    rows_extracted  INTEGER,
    rows_rejected   INTEGER,
    fact_rows_inserted INTEGER,
    fact_rows_updated  INTEGER,
    error_message   TEXT
);

-- One row per pipeline: the high-water mark of order_purchase_timestamp
-- that has been loaded into the warehouse.
CREATE TABLE IF NOT EXISTS audit.etl_watermark (
    pipeline_name   TEXT PRIMARY KEY,
    watermark_value TIMESTAMP   NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    run_id          BIGINT REFERENCES audit.pipeline_runs (run_id)
);

CREATE TABLE IF NOT EXISTS audit.dq_check_results (
    run_id       BIGINT REFERENCES audit.pipeline_runs (run_id),
    check_name   TEXT    NOT NULL,
    table_name   TEXT    NOT NULL,
    check_type   TEXT    NOT NULL,   -- null_pk, duplicate, invalid_date, foreign_key, invalid_number, domain
    severity     TEXT    NOT NULL CHECK (severity IN ('error', 'warn')),
    rows_checked INTEGER NOT NULL,
    rows_failed  INTEGER NOT NULL,
    passed       BOOLEAN NOT NULL,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, check_name)
);

-- Rows excluded from the warehouse because they failed an error-level check.
CREATE TABLE IF NOT EXISTS audit.rejected_records (
    run_id      BIGINT REFERENCES audit.pipeline_runs (run_id),
    table_name  TEXT NOT NULL,
    record_key  TEXT,
    check_name  TEXT NOT NULL,
    rejected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_rejected_run ON audit.rejected_records (run_id);

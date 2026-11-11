-- Operational view: recent pipeline runs and data-quality issues.
SELECT r.run_id,
       r.status,
       r.started_at::timestamp(0)                       AS started_at,
       EXTRACT(EPOCH FROM r.finished_at - r.started_at)::int AS seconds,
       r.watermark_before,
       r.watermark_after,
       r.fact_rows_inserted,
       r.fact_rows_updated,
       r.rows_rejected,
       (SELECT COUNT(*) FROM audit.dq_check_results q
         WHERE q.run_id = r.run_id AND NOT q.passed)      AS checks_with_failures
FROM audit.pipeline_runs r
ORDER BY r.run_id;

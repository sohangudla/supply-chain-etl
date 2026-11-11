-- Monthly late-delivery trend with month-over-month change.
-- Techniques: chained CTEs, JOIN to dim_date, window function LAG().
WITH orders AS (
    SELECT f.order_id,
           MIN(d.year_month)        AS year_month,
           BOOL_OR(f.is_late)       AS is_late,
           MAX(f.days_late)         AS days_late,
           MAX(f.delivery_days)     AS delivery_days
    FROM warehouse.fact_order_items f
    JOIN warehouse.dim_date d ON d.date_key = f.purchase_date_key
    WHERE f.is_delivered
    GROUP BY f.order_id
),
monthly AS (
    SELECT year_month,
           COUNT(*)                                            AS delivered_orders,
           COUNT(*) FILTER (WHERE is_late)                     AS late_orders,
           ROUND(100.0 * COUNT(*) FILTER (WHERE is_late) / COUNT(*), 2) AS late_pct,
           ROUND(AVG(days_late) FILTER (WHERE is_late), 1)     AS avg_days_late_when_late,
           ROUND(AVG(delivery_days), 1)                        AS avg_delivery_days
    FROM orders
    GROUP BY year_month
    HAVING COUNT(*) >= 100               -- drop the sparse first/last months
)
SELECT year_month,
       delivered_orders,
       late_orders,
       late_pct,
       late_pct - LAG(late_pct) OVER (ORDER BY year_month) AS late_pct_change_vs_prev_month,
       avg_days_late_when_late,
       avg_delivery_days
FROM monthly
ORDER BY year_month;

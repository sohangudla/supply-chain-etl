-- Monthly revenue with running total, 3-month moving average and MoM growth.
-- Techniques: CTE, window frames (ROWS BETWEEN), LAG(), NULLIF for safe division.
WITH monthly AS (
    SELECT d.year_month,
           SUM(f.price)               AS revenue,
           COUNT(DISTINCT f.order_id) AS orders
    FROM warehouse.fact_order_items f
    JOIN warehouse.dim_date d ON d.date_key = f.purchase_date_key
    WHERE f.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY d.year_month
)
SELECT year_month,
       orders,
       ROUND(revenue, 2)                                                     AS revenue_brl,
       ROUND(SUM(revenue) OVER (ORDER BY year_month), 2)                     AS running_total_brl,
       ROUND(AVG(revenue) OVER (ORDER BY year_month
                                ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS moving_avg_3m_brl,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY year_month))
             / NULLIF(LAG(revenue) OVER (ORDER BY year_month), 0), 1)        AS mom_growth_pct
FROM monthly
ORDER BY year_month;

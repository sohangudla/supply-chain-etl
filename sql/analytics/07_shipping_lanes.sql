-- Busiest seller-state -> customer-state shipping lanes and their performance.
-- A "lane" is a standard supply-chain/logistics concept.
-- Techniques: multi-JOIN, GROUP BY, window ROW_NUMBER() for ranking.
WITH lanes AS (
    SELECT s.state || ' -> ' || c.state                          AS lane,
           COUNT(DISTINCT f.order_id)                            AS orders,
           ROUND(AVG(f.delivery_days), 1)                        AS avg_delivery_days,
           ROUND(100.0 * AVG(CASE WHEN f.is_late THEN 1 ELSE 0 END), 1) AS late_pct,
           ROUND(AVG(f.freight_value), 2)                        AS avg_freight_brl
    FROM warehouse.fact_order_items f
    JOIN warehouse.dim_seller   s ON s.seller_key   = f.seller_key
    JOIN warehouse.dim_customer c ON c.customer_key = f.customer_key
    WHERE f.is_delivered
    GROUP BY s.state, c.state
)
SELECT ROW_NUMBER() OVER (ORDER BY orders DESC) AS lane_rank, *
FROM lanes
ORDER BY orders DESC
LIMIT 10;

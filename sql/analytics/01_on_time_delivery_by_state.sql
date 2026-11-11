-- On-time delivery % overall and by customer state.
-- Techniques: CTE, JOIN, GROUP BY ROLLUP, HAVING, conditional aggregation.
-- NOTE: the fact is at ITEM grain; delivery is an ORDER-level event, so we
-- first collapse to one row per order (otherwise multi-item orders count twice).
WITH delivered_orders AS (
    SELECT f.order_id,
           c.state,
           BOOL_OR(f.is_late) AS is_late          -- same value for every item of an order
    FROM warehouse.fact_order_items f
    JOIN warehouse.dim_customer c ON c.customer_key = f.customer_key
    WHERE f.is_delivered
    GROUP BY f.order_id, c.state
)
SELECT CASE WHEN GROUPING(state) = 1 THEN 'ALL' ELSE state END        AS customer_state,
       COUNT(*)                                                       AS delivered_orders,
       COUNT(*) FILTER (WHERE NOT is_late)                            AS on_time_orders,
       ROUND(100.0 * COUNT(*) FILTER (WHERE NOT is_late) / COUNT(*), 2) AS on_time_pct
FROM delivered_orders
GROUP BY ROLLUP (state)
HAVING COUNT(*) >= 500                    -- ignore states with too few orders to be meaningful
ORDER BY GROUPING(state) DESC, on_time_pct ASC;

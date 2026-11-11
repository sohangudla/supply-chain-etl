-- Sellers (with at least 50 delivered orders) whose late-delivery rate is
-- more than double the marketplace average: candidates for a supplier review.
-- Techniques: derived table (subquery in FROM), scalar subquery inside HAVING.
SELECT s.seller_id,
       s.state                                                   AS seller_state,
       COUNT(*)                                                  AS delivered_orders,
       ROUND(100.0 * AVG(CASE WHEN o.is_late THEN 1 ELSE 0 END), 2) AS late_pct,
       ROUND(AVG(o.delivery_days), 1)                            AS avg_delivery_days
FROM (
    -- one row per (order, seller): an order can be fulfilled by several sellers
    SELECT order_id, seller_key, BOOL_OR(is_late) AS is_late, MAX(delivery_days) AS delivery_days
    FROM warehouse.fact_order_items
    WHERE is_delivered
    GROUP BY order_id, seller_key
) o
JOIN warehouse.dim_seller s ON s.seller_key = o.seller_key
GROUP BY s.seller_id, s.state
HAVING COUNT(*) >= 50
   AND AVG(CASE WHEN o.is_late THEN 1 ELSE 0 END) > 2 * (
        SELECT AVG(CASE WHEN is_late THEN 1 ELSE 0 END)
        FROM (SELECT order_id, BOOL_OR(is_late) AS is_late
              FROM warehouse.fact_order_items WHERE is_delivered GROUP BY order_id) all_orders
   )
ORDER BY late_pct DESC;

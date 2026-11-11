-- Top 10 sellers by product revenue (price, excluding freight),
-- with their share of total revenue and cumulative share.
-- Techniques: CTE, JOIN, window functions RANK(), SUM() OVER () and running SUM().
WITH seller_revenue AS (
    SELECT s.seller_id,
           s.city,
           s.state,
           COUNT(DISTINCT f.order_id)  AS orders,
           SUM(f.price)                AS revenue
    FROM warehouse.fact_order_items f
    JOIN warehouse.dim_seller s ON s.seller_key = f.seller_key
    WHERE f.order_status NOT IN ('canceled', 'unavailable')
    GROUP BY s.seller_id, s.city, s.state
),
ranked AS (
    SELECT *,
           RANK() OVER (ORDER BY revenue DESC)                          AS revenue_rank,
           ROUND(100.0 * revenue / SUM(revenue) OVER (), 2)             AS pct_of_total,
           ROUND(100.0 * SUM(revenue) OVER (ORDER BY revenue DESC
                 ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
                 / SUM(revenue) OVER (), 2)                             AS cumulative_pct
    FROM seller_revenue
)
SELECT revenue_rank, seller_id, city, state, orders,
       ROUND(revenue, 2) AS revenue_brl, pct_of_total, cumulative_pct
FROM ranked
WHERE revenue_rank <= 10
ORDER BY revenue_rank;

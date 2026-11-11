-- Average and median delivery time by product category.
-- Techniques: JOIN, GROUP BY + HAVING, ordered-set aggregate PERCENTILE_CONT.
-- Item-level is correct here: each item belongs to exactly one category.
SELECT p.category_name_en                                            AS category,
       COUNT(*)                                                      AS delivered_items,
       ROUND(AVG(f.delivery_days), 2)                                AS avg_delivery_days,
       ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.delivery_days)::numeric, 2)
                                                                     AS median_delivery_days,
       ROUND(100.0 * AVG(CASE WHEN f.is_late THEN 1 ELSE 0 END), 2)  AS late_pct,
       ROUND(AVG(f.freight_value), 2)                                AS avg_freight_brl
FROM warehouse.fact_order_items f
JOIN warehouse.dim_product p ON p.product_key = f.product_key
WHERE f.is_delivered
GROUP BY p.category_name_en
HAVING COUNT(*) >= 200
ORDER BY avg_delivery_days DESC;

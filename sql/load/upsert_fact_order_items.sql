-- Fact upsert: translate natural keys -> surrogate keys via the dimensions,
-- then INSERT ... ON CONFLICT on the grain (order_id, order_item_id).
-- Re-running the same data therefore updates rows in place, never duplicates.
-- RETURNING (xmax = 0) is a PostgreSQL idiom: true for a freshly inserted row,
-- false for a row that was updated by ON CONFLICT.
WITH upserted AS (
    INSERT INTO warehouse.fact_order_items AS f (
        order_id, order_item_id, customer_key, product_key, seller_key, purchase_date_key,
        order_status, purchase_ts, approved_ts, delivered_carrier_ts, delivered_customer_ts,
        estimated_delivery_ts, shipping_limit_ts, price, freight_value, item_total,
        delivery_days, is_delivered, is_late, days_late, order_review_score, run_id)
    SELECT s.order_id, s.order_item_id, c.customer_key, p.product_key, sl.seller_key,
           s.purchase_date_key, s.order_status, s.purchase_ts, s.approved_ts,
           s.delivered_carrier_ts, s.delivered_customer_ts, s.estimated_delivery_ts,
           s.shipping_limit_ts, s.price, s.freight_value, s.item_total, s.delivery_days,
           s.is_delivered, s.is_late, s.days_late, s.order_review_score, :run_id
    FROM staging.fact_order_items s
    JOIN warehouse.dim_customer c  ON c.customer_id = s.customer_id
    JOIN warehouse.dim_product  p  ON p.product_id  = s.product_id
    JOIN warehouse.dim_seller   sl ON sl.seller_id  = s.seller_id
    ON CONFLICT (order_id, order_item_id) DO UPDATE
    SET customer_key = EXCLUDED.customer_key, product_key = EXCLUDED.product_key,
        seller_key = EXCLUDED.seller_key, purchase_date_key = EXCLUDED.purchase_date_key,
        order_status = EXCLUDED.order_status, purchase_ts = EXCLUDED.purchase_ts,
        approved_ts = EXCLUDED.approved_ts, delivered_carrier_ts = EXCLUDED.delivered_carrier_ts,
        delivered_customer_ts = EXCLUDED.delivered_customer_ts,
        estimated_delivery_ts = EXCLUDED.estimated_delivery_ts,
        shipping_limit_ts = EXCLUDED.shipping_limit_ts, price = EXCLUDED.price,
        freight_value = EXCLUDED.freight_value, item_total = EXCLUDED.item_total,
        delivery_days = EXCLUDED.delivery_days, is_delivered = EXCLUDED.is_delivered,
        is_late = EXCLUDED.is_late, days_late = EXCLUDED.days_late,
        order_review_score = EXCLUDED.order_review_score,
        run_id = EXCLUDED.run_id, loaded_at = now()
    RETURNING (xmax = 0) AS inserted
)
SELECT COUNT(*) FILTER (WHERE inserted)     AS inserted,
       COUNT(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted;

WITH upserted AS (
    INSERT INTO warehouse.fact_payments AS f (
        order_id, payment_sequential, customer_key, purchase_date_key,
        payment_type, installments, payment_value, run_id)
    SELECT s.order_id, s.payment_sequential, c.customer_key, s.purchase_date_key,
           s.payment_type, s.installments, s.payment_value, :run_id
    FROM staging.fact_payments s
    JOIN warehouse.dim_customer c ON c.customer_id = s.customer_id
    ON CONFLICT (order_id, payment_sequential) DO UPDATE
    SET customer_key = EXCLUDED.customer_key, purchase_date_key = EXCLUDED.purchase_date_key,
        payment_type = EXCLUDED.payment_type, installments = EXCLUDED.installments,
        payment_value = EXCLUDED.payment_value, run_id = EXCLUDED.run_id, loaded_at = now()
    RETURNING (xmax = 0) AS inserted
)
SELECT COUNT(*) FILTER (WHERE inserted)     AS inserted,
       COUNT(*) FILTER (WHERE NOT inserted) AS updated
FROM upserted;

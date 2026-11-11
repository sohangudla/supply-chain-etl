-- Dimension upserts (SCD Type 1: overwrite changed attributes, keep surrogate key).
-- The WHERE ... IS DISTINCT FROM clause skips rows that did not change, so a
-- rerun does not rewrite 100k identical rows.

INSERT INTO warehouse.dim_customer AS d (customer_id, customer_unique_id, zip_code_prefix, city, state)
SELECT customer_id, customer_unique_id, zip_code_prefix, city, state
FROM staging.dim_customer
ON CONFLICT (customer_id) DO UPDATE
SET customer_unique_id = EXCLUDED.customer_unique_id,
    zip_code_prefix    = EXCLUDED.zip_code_prefix,
    city               = EXCLUDED.city,
    state              = EXCLUDED.state,
    updated_at         = now()
WHERE (d.customer_unique_id, d.zip_code_prefix, d.city, d.state)
      IS DISTINCT FROM
      (EXCLUDED.customer_unique_id, EXCLUDED.zip_code_prefix, EXCLUDED.city, EXCLUDED.state);

INSERT INTO warehouse.dim_seller AS d (seller_id, zip_code_prefix, city, state)
SELECT seller_id, zip_code_prefix, city, state
FROM staging.dim_seller
ON CONFLICT (seller_id) DO UPDATE
SET zip_code_prefix = EXCLUDED.zip_code_prefix,
    city            = EXCLUDED.city,
    state           = EXCLUDED.state,
    updated_at      = now()
WHERE (d.zip_code_prefix, d.city, d.state)
      IS DISTINCT FROM (EXCLUDED.zip_code_prefix, EXCLUDED.city, EXCLUDED.state);

INSERT INTO warehouse.dim_product AS d (product_id, category_name_pt, category_name_en,
                                        weight_g, length_cm, height_cm, width_cm, photos_qty)
SELECT product_id, category_name_pt, category_name_en,
       weight_g, length_cm, height_cm, width_cm, photos_qty
FROM staging.dim_product
ON CONFLICT (product_id) DO UPDATE
SET category_name_pt = EXCLUDED.category_name_pt,
    category_name_en = EXCLUDED.category_name_en,
    weight_g = EXCLUDED.weight_g, length_cm = EXCLUDED.length_cm,
    height_cm = EXCLUDED.height_cm, width_cm = EXCLUDED.width_cm,
    photos_qty = EXCLUDED.photos_qty,
    updated_at = now()
WHERE (d.category_name_pt, d.category_name_en, d.weight_g, d.length_cm, d.height_cm, d.width_cm, d.photos_qty)
      IS DISTINCT FROM
      (EXCLUDED.category_name_pt, EXCLUDED.category_name_en, EXCLUDED.weight_g, EXCLUDED.length_cm,
       EXCLUDED.height_cm, EXCLUDED.width_cm, EXCLUDED.photos_qty);

INSERT INTO warehouse.dim_date
SELECT * FROM staging.dim_date
ON CONFLICT (date_key) DO NOTHING;

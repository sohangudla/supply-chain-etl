-- =====================================================================
-- Layered schemas
--   raw       : source CSVs landed unchanged (all TEXT) + lineage columns
--   staging   : cleaned, typed rows for the current run (truncated each run)
--   warehouse : star schema used for analytics
--   audit     : run history, watermarks, data-quality results, rejects
-- All statements are idempotent (IF NOT EXISTS) so this file can be rerun.
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS warehouse;
CREATE SCHEMA IF NOT EXISTS audit;

-- ---------- RAW: exact copy of the source files ----------
CREATE TABLE IF NOT EXISTS raw.orders (
    order_id TEXT, customer_id TEXT, order_status TEXT,
    order_purchase_timestamp TEXT, order_approved_at TEXT,
    order_delivered_carrier_date TEXT, order_delivered_customer_date TEXT,
    order_estimated_delivery_date TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.order_items (
    order_id TEXT, order_item_id TEXT, product_id TEXT, seller_id TEXT,
    shipping_limit_date TEXT, price TEXT, freight_value TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.order_payments (
    order_id TEXT, payment_sequential TEXT, payment_type TEXT,
    payment_installments TEXT, payment_value TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.order_reviews (
    review_id TEXT, order_id TEXT, review_score TEXT, review_comment_title TEXT,
    review_comment_message TEXT, review_creation_date TEXT, review_answer_timestamp TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.customers (
    customer_id TEXT, customer_unique_id TEXT, customer_zip_code_prefix TEXT,
    customer_city TEXT, customer_state TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.products (
    product_id TEXT, product_category_name TEXT, product_name_lenght TEXT,
    product_description_lenght TEXT, product_photos_qty TEXT, product_weight_g TEXT,
    product_length_cm TEXT, product_height_cm TEXT, product_width_cm TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.sellers (
    seller_id TEXT, seller_zip_code_prefix TEXT, seller_city TEXT, seller_state TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.geolocation (
    geolocation_zip_code_prefix TEXT, geolocation_lat TEXT, geolocation_lng TEXT,
    geolocation_city TEXT, geolocation_state TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS raw.category_translation (
    product_category_name TEXT, product_category_name_english TEXT,
    _source_file TEXT, _run_id BIGINT, _ingested_at TIMESTAMPTZ
);

-- =====================================================================
-- Star schema
--   Grain of the main fact: ONE ROW PER ORDER ITEM (order_id, order_item_id)
--
--            dim_date      dim_customer
--                 \          /
--              fact_order_items  ---- dim_product
--                 /
--           dim_seller
--   fact_payments (grain: one row per payment of an order) shares dim_date/dim_customer
-- =====================================================================

CREATE TABLE IF NOT EXISTS warehouse.dim_date (
    date_key     INTEGER PRIMARY KEY,          -- YYYYMMDD
    full_date    DATE    NOT NULL UNIQUE,
    year         SMALLINT NOT NULL,
    quarter      SMALLINT NOT NULL,
    month        SMALLINT NOT NULL,
    month_name   TEXT    NOT NULL,
    year_month   TEXT    NOT NULL,             -- '2018-03'
    day_of_month SMALLINT NOT NULL,
    day_of_week  SMALLINT NOT NULL,            -- 1 = Monday
    day_name     TEXT    NOT NULL,
    is_weekend   BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouse.dim_customer (
    customer_key        SERIAL PRIMARY KEY,    -- surrogate key
    customer_id         TEXT NOT NULL UNIQUE,  -- natural key (one per order in Olist)
    customer_unique_id  TEXT NOT NULL,         -- the real person
    zip_code_prefix     TEXT,
    city                TEXT,
    state               CHAR(2),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warehouse.dim_product (
    product_key        SERIAL PRIMARY KEY,
    product_id         TEXT NOT NULL UNIQUE,
    category_name_pt   TEXT,
    category_name_en   TEXT NOT NULL,          -- 'unknown' when missing
    weight_g           NUMERIC(10,2),
    length_cm          NUMERIC(10,2),
    height_cm          NUMERIC(10,2),
    width_cm           NUMERIC(10,2),
    photos_qty         SMALLINT,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warehouse.dim_seller (
    seller_key       SERIAL PRIMARY KEY,
    seller_id        TEXT NOT NULL UNIQUE,
    zip_code_prefix  TEXT,
    city             TEXT,
    state            CHAR(2),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS warehouse.fact_order_items (
    order_id                 TEXT     NOT NULL,
    order_item_id            SMALLINT NOT NULL,
    customer_key             INTEGER  NOT NULL REFERENCES warehouse.dim_customer (customer_key),
    product_key              INTEGER  NOT NULL REFERENCES warehouse.dim_product (product_key),
    seller_key               INTEGER  NOT NULL REFERENCES warehouse.dim_seller (seller_key),
    purchase_date_key        INTEGER  NOT NULL REFERENCES warehouse.dim_date (date_key),
    order_status             TEXT     NOT NULL,
    purchase_ts              TIMESTAMP NOT NULL,
    approved_ts              TIMESTAMP,
    delivered_carrier_ts     TIMESTAMP,
    delivered_customer_ts    TIMESTAMP,
    estimated_delivery_ts    TIMESTAMP,
    shipping_limit_ts        TIMESTAMP,
    price                    NUMERIC(12,2) NOT NULL CHECK (price > 0),
    freight_value            NUMERIC(12,2) NOT NULL CHECK (freight_value >= 0),
    item_total               NUMERIC(12,2) NOT NULL,
    delivery_days            NUMERIC(8,2),     -- purchase -> customer delivery
    is_delivered             BOOLEAN  NOT NULL,
    is_late                  BOOLEAN,          -- NULL when not delivered
    days_late                INTEGER,          -- >0 late, <=0 early/on time
    order_review_score       NUMERIC(3,2),     -- avg review score of the order
    run_id                   BIGINT   NOT NULL,
    loaded_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, order_item_id)
);
CREATE INDEX IF NOT EXISTS ix_foi_purchase_date ON warehouse.fact_order_items (purchase_date_key);
CREATE INDEX IF NOT EXISTS ix_foi_seller       ON warehouse.fact_order_items (seller_key);
CREATE INDEX IF NOT EXISTS ix_foi_product      ON warehouse.fact_order_items (product_key);

CREATE TABLE IF NOT EXISTS warehouse.fact_payments (
    order_id            TEXT     NOT NULL,
    payment_sequential  SMALLINT NOT NULL,
    customer_key        INTEGER  NOT NULL REFERENCES warehouse.dim_customer (customer_key),
    purchase_date_key   INTEGER  NOT NULL REFERENCES warehouse.dim_date (date_key),
    payment_type        TEXT     NOT NULL,
    installments        SMALLINT NOT NULL,
    payment_value       NUMERIC(12,2) NOT NULL CHECK (payment_value >= 0),
    run_id              BIGINT   NOT NULL,
    loaded_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, payment_sequential)
);

-- ---------- STAGING: same shape as the loads, natural keys only ----------
CREATE TABLE IF NOT EXISTS staging.dim_customer (LIKE warehouse.dim_customer INCLUDING DEFAULTS);
ALTER TABLE staging.dim_customer DROP COLUMN IF EXISTS customer_key;
CREATE TABLE IF NOT EXISTS staging.dim_product (LIKE warehouse.dim_product INCLUDING DEFAULTS);
ALTER TABLE staging.dim_product DROP COLUMN IF EXISTS product_key;
CREATE TABLE IF NOT EXISTS staging.dim_seller (LIKE warehouse.dim_seller INCLUDING DEFAULTS);
ALTER TABLE staging.dim_seller DROP COLUMN IF EXISTS seller_key;
CREATE TABLE IF NOT EXISTS staging.dim_date (LIKE warehouse.dim_date);

CREATE TABLE IF NOT EXISTS staging.fact_order_items (
    order_id TEXT, order_item_id SMALLINT, customer_id TEXT, product_id TEXT, seller_id TEXT,
    purchase_date_key INTEGER, order_status TEXT, purchase_ts TIMESTAMP, approved_ts TIMESTAMP,
    delivered_carrier_ts TIMESTAMP, delivered_customer_ts TIMESTAMP, estimated_delivery_ts TIMESTAMP,
    shipping_limit_ts TIMESTAMP, price NUMERIC(12,2), freight_value NUMERIC(12,2),
    item_total NUMERIC(12,2), delivery_days NUMERIC(8,2), is_delivered BOOLEAN, is_late BOOLEAN,
    days_late INTEGER, order_review_score NUMERIC(3,2)
);
CREATE TABLE IF NOT EXISTS staging.fact_payments (
    order_id TEXT, payment_sequential SMALLINT, customer_id TEXT, purchase_date_key INTEGER,
    payment_type TEXT, installments SMALLINT, payment_value NUMERIC(12,2)
);

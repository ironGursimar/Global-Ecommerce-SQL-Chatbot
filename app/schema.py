SCHEMA_SQL = r'''
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    age INTEGER,
    country_code TEXT,
    region TEXT,
    signup_date TEXT,
    loyalty_score REAL,
    email_open_rate REAL,
    discount_usage_rate REAL,
    avg_review_score REAL,
    referral_code TEXT,
    customer_tier TEXT,
    credit_limit REAL,
    noise_customer_0 REAL,
    noise_customer_1 REAL,
    noise_customer_2 REAL,
    noise_customer_3 REAL,
    noise_customer_4 REAL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    transaction_timestamp TEXT,
    order_value REAL,
    items_count INTEGER,
    payment_method TEXT,
    discount_applied INTEGER,
    shipping_speed TEXT,
    high_value_flag INTEGER,
    noise_trans_0 REAL,
    noise_trans_1 REAL
    ,FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    session_timestamp TEXT,
    session_duration REAL,
    pages_viewed INTEGER,
    cart_additions INTEGER,
    bounce_flag INTEGER,
    traffic_source TEXT,
    device_type TEXT,
    campaign_id INTEGER,
    geo_ip_region TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS marketing_campaigns (
    campaign_id INTEGER PRIMARY KEY,
    campaign_type TEXT,
    campaign_budget REAL,
    region_target TEXT,
    start_date TEXT,
    end_date TEXT
);

CREATE TABLE IF NOT EXISTS geo_data (
    geo_ip_region TEXT PRIMARY KEY,
    average_income REAL,
    urban_ratio REAL,
    internet_penetration REAL,
    region_tier TEXT
);

CREATE TABLE IF NOT EXISTS customer_targets (
    customer_id INTEGER PRIMARY KEY,
    target INTEGER,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE INDEX IF NOT EXISTS idx_tx_customer ON transactions(customer_id);
CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(transaction_timestamp);
CREATE INDEX IF NOT EXISTS idx_sess_customer ON sessions(customer_id);
CREATE INDEX IF NOT EXISTS idx_sess_date ON sessions(session_timestamp);
CREATE INDEX IF NOT EXISTS idx_sess_campaign ON sessions(campaign_id);
CREATE INDEX IF NOT EXISTS idx_sess_geo ON sessions(geo_ip_region);
CREATE INDEX IF NOT EXISTS idx_customer_country ON customers(country_code);
CREATE INDEX IF NOT EXISTS idx_customer_region ON customers(region);
CREATE INDEX IF NOT EXISTS idx_customer_tier ON customers(customer_tier);
'''

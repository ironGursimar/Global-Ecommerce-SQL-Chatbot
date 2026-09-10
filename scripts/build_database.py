import csv
import os
import sqlite3
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DATA = ROOT / "data"
DB = Path(os.getenv("DB_PATH", str(ROOT / "ecommerce.db")))
if not DB.is_absolute():
    DB = ROOT / DB


def num_money(v):
    if v is None or v == "":
        return None
    return float(str(v).replace("$", "").replace(",", "").strip())


def num_bool(v):
    if v is None or v == "":
        return None
    return 1 if str(v).strip().lower() in {"1", "true", "yes", "y"} else 0


def num_float(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def num_int(v):
    try: return int(v)
    except (TypeError, ValueError): return None

def norm_country(v):
    if v is None:
        return None
    s = str(v).strip().lower()
    aliases = {"usa": "USA", "u.s.": "USA", "us": "USA", "united states": "USA", "united states of america": "USA"}
    return aliases.get(s, str(v).strip().upper())


def create_schema(conn):
    from app.schema import SCHEMA_SQL
    conn.executescript(SCHEMA_SQL)


def load_customers(conn):
    path = DATA / "customers.csv"
    sql = """INSERT INTO customers VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
    with path.open(newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        batch=[]
        for x in r:
            batch.append((int(x['customer_id']), num_int(x['age']), norm_country(x['country_code']), x['region'], x['signup_date'],
                num_float(x['loyalty_score']), num_float(x['email_open_rate']), num_float(x['discount_usage_rate']), num_float(x['avg_review_score']),
                x['referral_code'], x['customer_tier'], num_money(x['credit_limit']),
                *[num_float(x[f'noise_customer_{i}']) for i in range(5)]))
            if len(batch)>=5000:
                conn.executemany(sql,batch); batch.clear()
        if batch: conn.executemany(sql,batch)


def load_transactions(conn):
    path=DATA/'transactions.csv'; sql="INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    with path.open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); batch=[]
        for x in r:
            batch.append((int(x['transaction_id']),int(x['customer_id']),x['transaction_timestamp'],num_money(x['order_value']),int(x['items_count']),x['payment_method'],num_bool(x['discount_applied']),x['shipping_speed'],num_bool(x['high_value_flag']),num_float(x['noise_trans_0']),num_float(x['noise_trans_1'])))
            if len(batch)>=5000: conn.executemany(sql,batch); batch.clear()
        if batch: conn.executemany(sql,batch)


def load_sessions(conn):
    path=DATA/'sessions.csv'; sql="INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)"
    with path.open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); batch=[]
        for x in r:
            batch.append((int(x['session_id']),int(x['customer_id']),x['session_timestamp'],num_float(x['session_duration']),num_int(x['pages_viewed']),num_int(x['cart_additions']),num_bool(x['bounce_flag']),x['traffic_source'],(x['device_type'].lower() if x['device_type'] else x['device_type']),num_int(x['campaign_id']),x['geo_ip_region']))
            if len(batch)>=10000: conn.executemany(sql,batch); batch.clear()
        if batch: conn.executemany(sql,batch)


def load_marketing(conn):
    path=DATA/'marketing_campaigns.csv'; sql="INSERT INTO marketing_campaigns VALUES (?,?,?,?,?,?)"
    with path.open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); conn.executemany(sql,[(num_int(x['campaign_id']),x['campaign_type'],num_money(x['campaign_budget']),x['region_target'],x['start_date'],x['end_date']) for x in r])


def load_geo(conn):
    path=DATA/'geo_data.csv'; sql="INSERT INTO geo_data VALUES (?,?,?,?,?)"
    with path.open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); conn.executemany(sql,[(x['geo_ip_region'],float(x['average_income']),float(x['urban_ratio']),float(x['internet_penetration']),x['region_tier']) for x in r])


def load_targets(conn):
    path=DATA/'train.csv'; sql="INSERT INTO customer_targets VALUES (?,?)"
    with path.open(newline='',encoding='utf-8') as f:
        r=csv.DictReader(f); conn.executemany(sql,[(int(x['customer_id']),int(x['target'])) for x in r])


if __name__ == '__main__':
    DB.parent.mkdir(parents=True, exist_ok=True)
    if DB.exists(): DB.unlink()
    conn=sqlite3.connect(DB)
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        create_schema(conn)
        print('Loading customers...'); load_customers(conn)
        print('Loading transactions...'); load_transactions(conn)
        print('Loading sessions...'); load_sessions(conn)
        print('Loading campaigns...'); load_marketing(conn)
        print('Loading geo...'); load_geo(conn)
        print('Loading train targets...'); load_targets(conn)
        conn.commit()
        print('Running ANALYZE...'); conn.execute('ANALYZE')
        conn.commit()
        print(f'Database created: {DB}')
    finally:
        conn.close()

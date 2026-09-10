import sqlite3
from pathlib import Path
from .config import DB_PATH

COUNTRY_EXPR = "CASE WHEN lower(c.country_code) IN ('usa','u.s.','us','united states','united states of america') THEN 'USA' ELSE upper(c.country_code) END"
CUSTOMER_DIMS = {'country': COUNTRY_EXPR, 'region':'c.region', 'tier':'c.customer_tier'}
TX_DIMS = {**CUSTOMER_DIMS, 'payment_method':'t.payment_method', 'shipping_speed':'t.shipping_speed'}
SESSION_DIMS = {**CUSTOMER_DIMS, 'traffic_source':'s.traffic_source', 'device_type':'s.device_type'}
CAMPAIGN_DIMS = {'campaign_type':'mc.campaign_type', 'region':'mc.region_target'}
GEO_DIMS = {'region_tier':'g.region_tier', 'region':'g.geo_ip_region'}

class SQLAnalytics:
    def __init__(self, db_path=DB_PATH): self.db_path=db_path
    def _conn(self):
        if not Path(self.db_path).is_file():
            raise FileNotFoundError(f'Database not found: {self.db_path}')
        c=sqlite3.connect(self.db_path, timeout=10)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA query_only=ON')
        return c
    def execute(self,s):
        if s['intent']=='lookup': return self.lookup(s)
        if s['intent']=='trend': return self.trend(s)
        if s['metric'] in ('spend','aov','transactions','items') and s['dimension'] in TX_DIMS: return self.transaction_group(s)
        if s['metric'] in ('sessions','session_duration','bounce_rate') and s['dimension'] in SESSION_DIMS: return self.session_group(s)
        if s['metric'] in ('campaign_budget',) and s['dimension'] in CAMPAIGN_DIMS: return self.campaign_group(s)
        if s['metric'] in ('income',) and s['dimension'] in GEO_DIMS: return self.geo_group(s)
        if s['metric'] in ('target_rate',) and s['dimension'] in CUSTOMER_DIMS: return self.target_group(s)
        if s['metric']=='customers' and s['dimension'] in CUSTOMER_DIMS: return self.customer_group(s)
        raise ValueError('This combination is not supported yet. Try a customer, transaction, session, campaign, geo, or target question.')

    def _order(self,s): return 'DESC' if s['order']=='desc' else 'ASC'
    def _limit(self,s): return int(s['limit'])
    def _date_where(self,s,col,params):
        w=[]
        if s.get('start_date'): w.append(f'{col} >= ?'); params.append(s['start_date'])
        if s.get('end_date'):
            w.append(f"{col} < date(?, '+1 day')"); params.append(s['end_date'])
        return w

    def transaction_group(self,s):
        dim=TX_DIMS[s['dimension']]; params=[]; where=self._date_where(s,'t.transaction_timestamp',params)
        if s.get('value'):
            if s['dimension']=='country': where.append(f'{COUNTRY_EXPR}=?'); params.append(s['value'].upper())
            elif s['dimension']=='region': where.append('c.region=?'); params.append(s['value'])
            elif s['dimension']=='tier': where.append('c.customer_tier=?'); params.append(s['value'])
            elif s['dimension']=='payment_method': where.append('t.payment_method=?'); params.append(s['value'])
            elif s['dimension']=='shipping_speed': where.append('t.shipping_speed=?'); params.append(s['value'])
        expr={'spend':'SUM(t.order_value)','aov':'AVG(t.order_value)','transactions':'COUNT(DISTINCT t.transaction_id)','items':'SUM(t.items_count)'}[s['metric']]
        sql=f'''SELECT {dim} AS dimension, {expr} AS value
FROM transactions t JOIN customers c ON c.customer_id=t.customer_id'''
        if where: sql+=' WHERE '+' AND '.join(where)
        sql+=f' GROUP BY {dim} ORDER BY value {self._order(s)} LIMIT {self._limit(s)}'
        return self._run(sql,params)

    def session_group(self,s):
        dim=SESSION_DIMS[s['dimension']]; params=[]; where=self._date_where(s,'s.session_timestamp',params)
        if s.get('value'):
            if s['dimension']=='country': where.append(f'{COUNTRY_EXPR}=?'); params.append(s['value'].upper())
            elif s['dimension']=='region': where.append('c.region=?'); params.append(s['value'])
            elif s['dimension']=='tier': where.append('c.customer_tier=?'); params.append(s['value'])
            elif s['dimension']=='traffic_source': where.append('s.traffic_source=?'); params.append(s['value'])
            elif s['dimension']=='device_type': where.append('s.device_type=?'); params.append(s['value'])
        expr={'sessions':'COUNT(DISTINCT s.session_id)','session_duration':'AVG(s.session_duration)','bounce_rate':'AVG(s.bounce_flag)'}[s['metric']]
        sql=f'''SELECT {dim} AS dimension, {expr} AS value
FROM sessions s JOIN customers c ON c.customer_id=s.customer_id'''
        if where: sql+=' WHERE '+' AND '.join(where)
        sql+=f' GROUP BY {dim} ORDER BY value {self._order(s)} LIMIT {self._limit(s)}'
        return self._run(sql,params)

    def campaign_group(self,s):
        dim=CAMPAIGN_DIMS[s['dimension']].replace('mc.','cb.')
        sql=f"""WITH campaign_base AS (
  SELECT campaign_id, campaign_type, region_target, campaign_budget
  FROM marketing_campaigns
)
SELECT {dim} AS dimension, SUM(cb.campaign_budget) AS value
FROM campaign_base cb
GROUP BY {dim} ORDER BY value {self._order(s)} LIMIT {self._limit(s)}"""
        return self._run(sql,[])

    def geo_group(self,s):
        dim=GEO_DIMS[s['dimension']]; sql=f'''SELECT {dim} AS dimension, AVG(g.average_income) AS value
FROM geo_data g JOIN sessions s ON s.geo_ip_region=g.geo_ip_region JOIN customers c ON c.customer_id=s.customer_id
GROUP BY {dim} ORDER BY value {self._order(s)} LIMIT {self._limit(s)}'''
        return self._run(sql,[])

    def target_group(self,s):
        dim=CUSTOMER_DIMS[s['dimension']]; sql=f'''SELECT {dim} AS dimension, AVG(ct.target) AS value
FROM customer_targets ct JOIN customers c ON c.customer_id=ct.customer_id
GROUP BY {dim} ORDER BY value {self._order(s)} LIMIT {self._limit(s)}'''
        return self._run(sql,[])

    def customer_group(self,s):
        dim=CUSTOMER_DIMS[s['dimension']]; sql=f'''SELECT {dim} AS dimension, COUNT(DISTINCT c.customer_id) AS value
FROM customers c LEFT JOIN customer_targets ct ON ct.customer_id=c.customer_id
GROUP BY {dim} ORDER BY value {self._order(s)} LIMIT {self._limit(s)}'''
        return self._run(sql,[])

    def lookup(self,s):
        sql='''WITH tx AS (
  SELECT customer_id, SUM(order_value) total_spend, AVG(order_value) aov, COUNT(*) transactions, SUM(items_count) items
  FROM transactions GROUP BY customer_id
), sess AS (
  SELECT customer_id, COUNT(*) sessions, AVG(session_duration) avg_session_duration,
         AVG(pages_viewed) avg_pages_viewed, AVG(cart_additions) avg_cart_additions,
         AVG(bounce_flag) bounce_rate
  FROM sessions GROUP BY customer_id
)
SELECT c.customer_id,c.age,
       CASE WHEN lower(c.country_code) IN ('usa','u.s.','us','united states','united states of america') THEN 'USA' ELSE upper(c.country_code) END country,
       c.region,c.customer_tier,c.loyalty_score,c.avg_review_score,
       tx.total_spend,tx.aov,tx.transactions,tx.items,
       sess.sessions,sess.avg_session_duration,sess.avg_pages_viewed,sess.avg_cart_additions,sess.bounce_rate,
       ct.target
FROM customers c
LEFT JOIN tx ON tx.customer_id=c.customer_id
LEFT JOIN sess ON sess.customer_id=c.customer_id
LEFT JOIN customer_targets ct ON ct.customer_id=c.customer_id
WHERE c.customer_id=?'''
        return self._run(sql,[s['customer_id']])

    def trend(self,s):
        sql='''SELECT substr(t.transaction_timestamp,1,7) AS dimension,
                      SUM(t.order_value) AS value
               FROM transactions t JOIN customers c ON c.customer_id=t.customer_id'''
        params=[]; w=self._date_where(s,'t.transaction_timestamp',params)
        if w: sql+=' WHERE '+' AND '.join(w)
        sql+=' GROUP BY substr(t.transaction_timestamp,1,7) ORDER BY dimension ASC'
        return self._run(sql,params)

    def _run(self,sql,params):
        with self._conn() as c: rows=[dict(r) for r in c.execute(sql,params).fetchall()]
        return {'sql':sql,'params':params,'rows':rows}

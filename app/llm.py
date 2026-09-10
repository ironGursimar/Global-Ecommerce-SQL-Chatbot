import json
import logging
import re
from typing import Any
import requests
from .config import (
    LLM_PROVIDER, GEMINI_API_KEY, GEMINI_MODEL, OLLAMA_MODEL,
    OLLAMA_BASE_URL, LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

ALLOWED = {
    'intent': ['ranking','average','count','lookup','trend','comparison'],
    'metric': ['spend','aov','transactions','customers','sessions','session_duration','items','discount_rate','bounce_rate','income','campaign_budget','target_rate'],
    'dimension': ['country','region','tier','payment_method','traffic_source','device_type','campaign_type','region_tier','shipping_speed','customer','date'],
    'aggregation': ['sum','avg','count','count_distinct','min','max'],
    'order': ['asc','desc'],
}

SYSTEM_PROMPT = '''You are the intent parser for a global e-commerce analytics chatbot.
Return ONLY valid JSON. Never write SQL. Never invent fields outside this schema.
The backend executes a safe SQL template after validation.

JSON keys:
intent: ranking | average | count | lookup | trend | comparison
metric: spend | aov | transactions | customers | sessions | session_duration | items | discount_rate | bounce_rate | income | campaign_budget | target_rate
 dimension: country | region | tier | payment_method | traffic_source | device_type | campaign_type | region_tier | shipping_speed | customer | date
aggregation: sum | avg | count | count_distinct | min | max
order: asc | desc
limit: integer 1-20
customer_id: integer or null
start_date: YYYY-MM-DD or null
end_date: YYYY-MM-DD or null
value: string or null
second_value: string or null

Semantics:
- "total spend" / "money spent" => metric spend, aggregation sum.
- "average order value" => aov, aggregation avg.
- "how many transactions/orders" => transactions, count.
- "how many customers" => customers, count_distinct.
- "sessions/visits" => sessions, count.
- "average session duration" => session_duration, avg.
- "discount usage" => discount_rate, avg.
- "bounce rate" => bounce_rate, avg.
- "average income" => income, avg.
- "campaign budget" => campaign_budget, sum or avg depending wording.
- "purchase target rate" => target_rate, avg.
- "top/highest/most" => ranking + desc.
- "lowest/bottom" => ranking + asc.
- "by country/region/tier/..." => dimension accordingly.
- A customer id question should use intent lookup and customer_id.
- If a filter value is explicitly given, put it in value (e.g. USA, Gold, mobile).
- Date phrases must become start_date/end_date when possible.
- If limit is not specified for a ranking, use 5.
'''


def _extract_json(text: str) -> dict[str, Any]:
    text=text.strip()
    if text.startswith('```'):
        text=re.sub(r'^```(?:json)?\s*|\s*```$','',text,flags=re.I|re.S)
    start=text.find('{'); end=text.rfind('}')
    if start<0 or end<start: raise ValueError('LLM did not return JSON')
    return json.loads(text[start:end+1])


def rule_fallback(q: str) -> dict[str, Any]:
    s=q.lower().strip()
    out={'intent':'average','metric':'aov','dimension':'country','aggregation':'avg','order':'desc','limit':5,'customer_id':None,'start_date':None,'end_date':None,'value':None,'second_value':None}
    m=re.search(r'customer\s*(?:id\s*)?(\d+)',s)
    if m:
        out.update(intent='lookup', customer_id=int(m.group(1)))
        if 'transaction' in s or 'order' in s: out['metric']='transactions'
        elif 'session' in s: out['metric']='sessions'
        elif 'spend' in s or 'spent' in s: out['metric']='spend'
        return out
    if any(x in s for x in ['highest','top','most','largest','best']): out['intent']='ranking'; out['order']='desc'
    elif any(x in s for x in ['lowest','bottom','least','smallest','worst']): out['intent']='ranking'; out['order']='asc'
    elif ('total' in s or 'sum' in s) and 'by ' in s: out['intent']='ranking'; out['order']='desc'; out['aggregation']='sum'
    elif any(x in s for x in ['how many','count','number of']): out['intent']='count'; out['aggregation']='count'
    elif 'trend' in s or 'over time' in s or 'by month' in s: out['intent']='trend'; out['dimension']='date'
    else: out['intent']='average'; out['aggregation']='avg'
    if 'spend' in s or 'spent' in s: out['metric']='spend'; out['aggregation']='sum' if out['intent']=='ranking' else 'avg'
    elif 'aov' in s or 'average order value' in s or 'order value' in s: out['metric']='aov'; out['aggregation']='avg'
    elif 'transaction' in s or 'order' in s: out['metric']='transactions'; out['aggregation']='count'
    elif 'session duration' in s: out['metric']='session_duration'; out['aggregation']='avg'
    elif 'session' in s: out['metric']='sessions'; out['aggregation']='count'
    elif 'bounce' in s: out['metric']='bounce_rate'; out['aggregation']='avg'
    elif 'discount' in s: out['metric']='discount_rate'; out['aggregation']='avg'
    elif 'income' in s: out['metric']='income'; out['aggregation']='avg'
    elif 'budget' in s: out['metric']='campaign_budget'; out['aggregation']='sum'
    elif 'target' in s or 'purchase' in s: out['metric']='target_rate'; out['aggregation']='avg'
    if 'country' in s: out['dimension']='country'
    elif 'region tier' in s: out['dimension']='region_tier'
    elif 'region' in s: out['dimension']='region'
    elif 'tier' in s: out['dimension']='tier'
    elif 'payment' in s: out['dimension']='payment_method'
    elif 'traffic' in s or 'source' in s: out['dimension']='traffic_source'
    elif 'device' in s: out['dimension']='device_type'
    elif 'campaign type' in s: out['dimension']='campaign_type'
    elif 'shipping' in s: out['dimension']='shipping_speed'
    lim=re.search(r'(?:top|bottom)\s+(\d+)',s)
    if lim: out['limit']=min(20,int(lim.group(1)))
    if 'usa' in s or 'u.s.' in s or 'us ' in s: out['value']='USA'
    return out


def parse_question(question: str) -> dict[str, Any]:
    question = question.strip()
    provider=LLM_PROVIDER
    if provider=='auto':
        if GEMINI_API_KEY: provider='gemini'
        else:
            try:
                r=requests.get(f'{OLLAMA_BASE_URL}/api/tags',timeout=min(LLM_TIMEOUT_SECONDS, 2))
                provider='ollama' if r.ok else 'fallback'
            except requests.RequestException:
                provider='fallback'
    if provider=='gemini':
        try:
            from google import genai
            from google.genai import types
            client=genai.Client(api_key=GEMINI_API_KEY)
            schema={"type":"OBJECT","properties":{
                "intent":{"type":"STRING","enum":ALLOWED['intent']},"metric":{"type":"STRING","enum":ALLOWED['metric']},"dimension":{"type":"STRING","enum":ALLOWED['dimension']},"aggregation":{"type":"STRING","enum":ALLOWED['aggregation']},"order":{"type":"STRING","enum":ALLOWED['order']},"limit":{"type":"INTEGER"},"customer_id":{"type":"INTEGER","nullable":True},"start_date":{"type":"STRING","nullable":True},"end_date":{"type":"STRING","nullable":True},"value":{"type":"STRING","nullable":True},"second_value":{"type":"STRING","nullable":True}},"required":["intent","metric","dimension","aggregation","order","limit","customer_id","start_date","end_date","value","second_value"]}
            resp=client.models.generate_content(model=GEMINI_MODEL,contents=SYSTEM_PROMPT+'\nUSER QUESTION:\n'+question,config=types.GenerateContentConfig(response_mime_type='application/json',response_schema=schema,temperature=0))
            return _validate(_extract_json(resp.text))
        except (ImportError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            logger.warning("Gemini parsing failed; using fallback parser: %s", exc)
    if provider=='ollama':
        try:
            payload={'model':OLLAMA_MODEL,'messages':[{'role':'system','content':SYSTEM_PROMPT},{'role':'user','content':question}],'stream':False,'format':'json','options':{'temperature':0}}
            r=requests.post(f'{OLLAMA_BASE_URL}/api/chat',json=payload,timeout=LLM_TIMEOUT_SECONDS); r.raise_for_status()
            return _validate(_extract_json(r.json()['message']['content']))
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            logger.warning("Ollama parsing failed; using fallback parser: %s", exc)
    return _validate(rule_fallback(question))


def _validate(q: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(q, dict):
        raise ValueError('Parser response must be an object')
    for k in ALLOWED:
        if q.get(k) not in ALLOWED[k]:
            raise ValueError(f'Invalid {k}: {q.get(k)}')
    q['limit']=max(1,min(20,int(q.get('limit') or 5)))
    if q.get('customer_id') is not None: q['customer_id']=int(q['customer_id'])
    for key in ('start_date', 'end_date'):
        if q.get(key) is not None and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(q[key])):
            raise ValueError(f'Invalid {key}')
    for key in ('value', 'second_value'):
        if q.get(key) is not None:
            q[key] = str(q[key]).strip()[:100] or None
    return q

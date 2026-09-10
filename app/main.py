from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .llm import parse_question
from .sql_engine import SQLAnalytics
from .config import BASE_DIR, EXPOSE_SQL, MAX_QUESTION_LENGTH
import sqlite3

@asynccontextmanager
async def lifespan(_app):
    yield

app=FastAPI(title='Global E-Commerce SQL Chatbot', version='1.0.0', lifespan=lifespan)
engine=SQLAnalytics()
app.mount('/static',StaticFiles(directory=BASE_DIR / 'static'),name='static')

class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_LENGTH)

@app.get('/')
def home(): return FileResponse(BASE_DIR / 'static' / 'index.html')

@app.get('/health')
def health():
    try:
        with sqlite3.connect(engine.db_path, timeout=2) as conn:
            conn.execute('SELECT 1').fetchone()
        return {'ok': True}
    except (sqlite3.Error, OSError):
        raise HTTPException(503, 'Database is unavailable')

@app.post('/chat')
def chat(req:ChatRequest):
    question = req.question.strip()
    if not question: raise HTTPException(422,'Question is empty')
    try:
        spec=parse_question(question)
        result=engine.execute(spec)
        response = {'question':question,'spec':spec,'answer':format_answer(question,spec,result['rows']),'rows':result['rows']}
        if EXPOSE_SQL:
            response.update(sql=result['sql'], params=result['params'])
        return response
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except sqlite3.Error:
        raise HTTPException(503, 'The analytics database could not complete the request')

def fmt(v):
    if v is None: return '0'
    if isinstance(v,float): return f'{v:,.2f}'
    if isinstance(v,int): return f'{v:,}'
    return str(v)

COUNTRY_NAMES = {'USA': 'United States', 'UK': 'United Kingdom', 'DE': 'Germany', 'FR': 'France', 'IN': 'India'}

def display_dimension(value):
    return COUNTRY_NAMES.get(str(value), str(value))

def metric_label(spec):
    return {
        'spend': 'total spend', 'aov': 'average order value', 'transactions': 'purchases',
        'customers': 'customers', 'sessions': 'sessions', 'session_duration': 'average session duration',
        'items': 'items purchased', 'discount_rate': 'discount usage rate', 'bounce_rate': 'bounce rate',
        'income': 'average income', 'campaign_budget': 'campaign budget', 'target_rate': 'purchase target rate',
    }.get(spec['metric'], spec['metric'])

def format_value(value, spec):
    if value is None: return '0'
    if spec['metric'] in {'spend', 'aov', 'income', 'campaign_budget'}: return f'${float(value):,.2f}'
    if spec['metric'] in {'discount_rate', 'bounce_rate', 'target_rate'}: return f'{float(value) * 100:.1f}%'
    if spec['metric'] == 'session_duration': return f'{float(value):,.1f} seconds'
    if isinstance(value, float) and value.is_integer(): return f'{int(value):,}'
    if isinstance(value, float): return f'{value:,.2f}'
    return f'{value:,}' if isinstance(value, int) else str(value)

def format_answer(q,spec,rows):
    if not rows: return 'I could not find matching data for that question.'
    if spec['intent']=='lookup':
        r=rows[0]; parts=[f"Customer {r['customer_id']} is in {r['country']} ({r['customer_tier']} tier)."]
        if r.get('total_spend') is not None: parts.append(f"Total spend: ${fmt(r['total_spend'])}; AOV: ${fmt(r['aov'])}; purchases: {fmt(r['transactions'])}.")
        if r.get('sessions') is not None: parts.append(f"Sessions: {fmt(r['sessions'])}; average session duration: {fmt(r['avg_session_duration'])} seconds.")
        if r.get('target') is not None: parts.append(f"Training target: {r['target']}.")
        return '**Customer profile**\n\n' + ' '.join(parts)
    if len(rows)==1:
        row = rows[0]
        return f"**{display_dimension(row['dimension'])}** has **{format_value(row['value'], spec)} {metric_label(spec)}**."
    label = metric_label(spec)
    first = rows[0]
    lines = [f"**{display_dimension(first['dimension'])} leads in {label}** with **{format_value(first['value'], spec)}**.", '',
             f'| Rank | {spec["dimension"].title()} | {label.title()} |', '|---:|---|---:|']
    lines.extend(f'| {i} | {display_dimension(r["dimension"])} | {format_value(r["value"], spec)} |' for i, r in enumerate(rows, 1))
    if len(rows) > 1 and float(rows[1]['value'] or 0):
        ratio = float(first['value']) / float(rows[1]['value'])
        lines.extend(['', f'{display_dimension(first["dimension"])} is approximately **{ratio:.1f}x** the second-ranked result.'])
    return '\n'.join(lines)

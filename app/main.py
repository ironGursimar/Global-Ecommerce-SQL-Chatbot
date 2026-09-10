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

def format_answer(q,spec,rows):
    if not rows: return 'I could not find matching data for that question.'
    if spec['intent']=='lookup':
        r=rows[0]; parts=[f"Customer {r['customer_id']} is in {r['country']} ({r['customer_tier']} tier)."]
        if r.get('total_spend') is not None: parts.append(f"Total spend: ${fmt(r['total_spend'])}; AOV: ${fmt(r['aov'])}; transactions: {fmt(r['transactions'])}.")
        if r.get('sessions') is not None: parts.append(f"Sessions: {fmt(r['sessions'])}; average session duration: {fmt(r['avg_session_duration'])} seconds.")
        if r.get('target') is not None: parts.append(f"Training target: {r['target']}.")
        return ' '.join(parts)
    if len(rows)==1:
        return f"{rows[0]['dimension']}: {fmt(rows[0]['value'])}"
    return '\n'.join([f"{i+1}. {r['dimension']}: {fmt(r['value'])}" for i,r in enumerate(rows)])

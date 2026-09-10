@echo off
setlocal
if not exist ecommerce.db (
  echo ecommerce.db not found. Run: python scripts\build_database.py
  exit /b 1
)
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

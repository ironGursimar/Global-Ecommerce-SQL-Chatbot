#!/usr/bin/env bash
set -e
if [ ! -f ecommerce.db ]; then
  echo "ecommerce.db not found. Run: python scripts/build_database.py" >&2
  exit 1
fi
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

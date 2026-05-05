#!/bin/bash
set -e

# Ensure report directories exist in the bind-mounted volume
mkdir -p /app/data/reports/incoming \
         /app/data/reports/archive \
         /app/data/logs

echo "==> Running Alembic migrations..."
alembic upgrade head

echo "==> Seeding initial data..."
python docker/seed.py

echo "==> Starting API server on :8000..."
exec uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
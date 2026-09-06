#!/usr/bin/env bash
set -e

# Run database migrations before service start if RUN_MIGRATIONS=true
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "[entrypoint] Running database migrations via Alembic..."
    alembic upgrade head
fi

case "$1" in
    api)
        echo "[entrypoint] Starting WeatherGPT API Server on port ${PORT:-8000}..."
        exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${UVICORN_WORKERS:-2}"
        ;;
    worker|scheduler)
        echo "[entrypoint] Starting WeatherGPT Background Scheduler & Ingestion Worker..."
        exec python -m app.pipelines.scheduler
        ;;
    migrate)
        echo "[entrypoint] Executing Alembic database migrations..."
        exec alembic upgrade head
        ;;
    *)
        exec "$@"
        ;;
esac

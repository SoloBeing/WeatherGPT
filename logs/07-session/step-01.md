# Session 07 — Step 01: Production Multi-Stage Dockerfile & Container Environment

**What was done:**
- Created `.dockerignore` to cleanly isolate container build context from local virtualenvs (`.venv`), bytecode caches (`__pycache__`), test artifacts (`.pytest_cache`), git metadata, and local development stores.
- Implemented production multi-stage `Dockerfile` using Astral `uv`:
  - **Stage 1 (Builder):** `python:3.13-slim-bookworm` with official Astral `uv` binaries (`ghcr.io/astral-sh/uv:0.6.14`), building c-extensions, and installing frozen locked dependencies (`uv sync --frozen --no-dev`) into `/app/.venv`.
  - **Stage 2 (Runtime):** Lean `python:3.13-slim-bookworm` base image with runtime dependencies (`curl`, `libpq5`, `ffmpeg`), non-root system user `weathergpt` (UID/GID 10001), virtualenv copied from builder, healthcheck hitting `/health`, and default `api` entrypoint.
- Implemented `docker/entrypoint.sh` supporting flexible role dispatch:
  - `api`: Starts Uvicorn ASGI server with configurable workers and port.
  - `worker` / `scheduler`: Runs background numerical ingestion and alert polling pipeline.
  - `migrate`: Runs Alembic database schema migrations (`alembic upgrade head`).
  - Automatic `RUN_MIGRATIONS=true` pre-start migration trigger.
- Verified test suite passes without regressions under strict `-W error` enforcement.

**Commands:**
```bash
uv lock --check
chmod +x docker/entrypoint.sh
uv run pytest
```

**Notable output:**
- `uv lock --check`: Resolved 135 packages in 8ms.
- Pytest verification: 35/35 passed in 11.73s with 0 warnings.

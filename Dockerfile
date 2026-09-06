# syntax=docker/dockerfile:1

# ------------------------------------------------------------------------------
# Stage 1: Builder (install dependencies using uv)
# ------------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS builder

# Install uv from official binary image
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

# Install build dependencies required for C-extensions and geospatial libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definition files
COPY pyproject.toml uv.lock ./

# Install project dependencies into virtual environment without installing the root package yet
RUN uv sync --frozen --no-install-project --no-dev

# ------------------------------------------------------------------------------
# Stage 2: Runtime (lean production image)
# ------------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

WORKDIR /app

# Install minimal runtime dependencies (curl for healthchecks, libpq for postgres, ffmpeg for voice audio)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group
RUN groupadd -g 10001 weathergpt && \
    useradd -u 10001 -g weathergpt -s /bin/bash -m -d /home/weathergpt weathergpt

# Copy pre-built virtual environment from builder stage
COPY --from=builder /app/.venv /app/.venv

# Configure environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

# Copy application configuration and source code
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh

# Set directory permissions
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    mkdir -p /app/data && \
    chown -R weathergpt:weathergpt /app

# Switch to non-root user
USER weathergpt

EXPOSE 8000

# Health check using FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

ENTRYPOINT ["entrypoint.sh"]
CMD ["api"]

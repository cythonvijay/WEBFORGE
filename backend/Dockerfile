# syntax=docker/dockerfile:1

# --- Stage 1: Dependency Builder ---
FROM python:3.12-slim-bookworm AS builder
WORKDIR /build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --prefix=/install --no-warn-script-location -r requirements.txt

# --- Stage 2: Hardened Production Runtime ---
FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONPATH=/app

RUN groupadd --system --gid 10001 webforge \
    && useradd --system --uid 10001 --gid webforge --create-home --home-dir /home/webforge webforge

COPY --from=builder /install /usr/local
COPY --chown=webforge:webforge alembic.ini ./alembic.ini
COPY --chown=webforge:webforge alembic ./alembic
COPY --chown=webforge:webforge app ./app
COPY --chown=webforge:webforge scripts ./scripts

USER webforge
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/api/health/live', timeout=3)"

# Apply migrations before serving traffic. Render's PORT is used when supplied;
# local Docker Compose falls back to port 8000.
CMD ["sh", "-c", "python -m scripts.db_ops migrate && exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --timeout-graceful-shutdown 30"]

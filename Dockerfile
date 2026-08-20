FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock.txt


FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONFAULTHANDLER=1 \
    PYTHONPATH=/app:/app/platform

RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

COPY --from=builder /install /usr/local

# The SEPHIROTH runtime package. Installed editable so `import sephiroth`
# resolves identically here, under pytest, and under uvicorn — adding `src` to
# PYTHONPATH would cover only some of those. See docs/00-migration-charter.md §4.
# Placed before platform/intelligence/data below: those change far more often
# than src/, so this ordering keeps the editable-install layer cached across
# most backend edits instead of invalidating it on every router change.
COPY pyproject.toml .
COPY src src/
RUN pip install --no-cache-dir --no-deps -e .

COPY platform platform/
COPY intelligence intelligence/
COPY data data/
COPY migrations migrations/
COPY alembic.ini .

# real_data/ is intentionally NOT copied: it's optional dev/demo-only
# sample data (Synthea patients+notes, DDInter drug interactions, RSNA
# imaging fixtures — see real_data/README.md), and some of it (DDInter,
# RSNA) carries non-commercial license terms unsuitable for a distributed
# production image. intelligence/mcp/drug_safety_server.py already
# degrades gracefully to its hand-curated table when the file is absent.

USER app

EXPOSE 8000

# Render injects $PORT; default 8000 preserves the previous behavior for
# any other environment that doesn't set it. `exec` keeps uvicorn as PID 1
# so it receives SIGTERM directly instead of a shell swallowing it and
# forcing a SIGKILL on every deploy. --proxy-headers/--forwarded-allow-ips
# trust Render's edge-terminated TLS proxy for X-Forwarded-*; without it
# every request.client/request.url reports the proxy, not the real caller
# (audit.py logs PHI access by caller). --no-access-log: request_logging
# middleware in api/main.py already logs one line per request.
CMD ["sh", "-c", "exec python -m uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive 65 --timeout-graceful-shutdown 20 --limit-concurrency 20 --no-access-log"]

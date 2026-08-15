FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

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

# `platform/` cannot be a Python package (it would shadow the stdlib module),
# so its subpackages (api, core, auth) are imported as top-level packages.
ENV PYTHONPATH=/app:/app/platform

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

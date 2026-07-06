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

# `platform/` cannot be a Python package (it would shadow the stdlib module),
# so its subpackages (api, core, auth) are imported as top-level packages.
ENV PYTHONPATH=/app:/app/platform

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

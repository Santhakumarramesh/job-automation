# API (default) or Celery worker — override CMD in orchestration.
# Build from repo root; .dockerignore trims context (tests, docs, scripts).
FROM python:3.12-slim-bookworm

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

COPY . /app/

RUN pip install --upgrade pip && pip install ".[production]"

EXPOSE 8000

# For Celery, override CMD; workers do not serve HTTP on 8000.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

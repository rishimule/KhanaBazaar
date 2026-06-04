# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1
RUN pip install --no-cache-dir uv

WORKDIR /app
# Deps-only layer: install dependencies without building the local `app`
# package (its source isn't copied yet). The app runs off PYTHONPATH below, so
# it never needs to be installed as a package.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY migrations ./migrations
COPY scripts ./scripts
COPY alembic.ini ./

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src"

# Cloud Run injects $PORT (default 8080). Overridden for worker/jobs.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]

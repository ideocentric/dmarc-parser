FROM python:3.14-slim AS base

# curl is used by the compose healthchecks. No compiler: every locked
# package ships a binary wheel for CPython 3.14 on x86_64 and aarch64.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure the data directory tree exists inside the image as a base layer
RUN mkdir -p data/reports/incoming data/reports/archive data/clients

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Test image: production plus the test and tooling packages from
# requirements-dev.txt. CI builds this one with `--target test`.
FROM base AS test
RUN pip install --no-cache-dir -r requirements-dev.txt

# Production image, without test tools. It stays the LAST stage, so a plain
# `docker build .` (compose, the deploy jobs) still produces it.
FROM base AS production

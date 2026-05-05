FROM python:3.14-slim

# Build dependencies needed for bcrypt and cryptography wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
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
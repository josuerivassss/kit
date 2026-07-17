FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Pillow (image processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY locales ./locales
COPY migrations ./migrations
COPY assets ./assets
RUN pip install -e . --no-deps

# Run as a non-root user (least privilege).
RUN useradd --create-home --shell /bin/bash bcommie
USER bcommie

ENTRYPOINT ["python", "-m", "bcommie.main"]

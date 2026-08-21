FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CREWAI_DISABLE_TELEMETRY=true \
    OTEL_SDK_DISABLED=true

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY docker-entrypoint.sh ./

RUN pip install --no-cache-dir . && \
    apt-get update && apt-get install -y --no-install-recommends gosu && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 1000 appuser && \
    mkdir -p /app/data && chown -R appuser:appuser /app && \
    chmod +x docker-entrypoint.sh

EXPOSE 8000

# Stays root here — docker-entrypoint.sh re-chowns the volume mount (which
# Railway attaches at start, after this image's build-time chown already
# ran) and then drops to appuser via gosu before exec'ing uvicorn.
ENTRYPOINT ["./docker-entrypoint.sh"]

# Railway injects $PORT at runtime; default 8000 for local/docker-compose use.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

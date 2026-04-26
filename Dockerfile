# ─────────────────────────────────────────────────────────────
# Stage 1: Builder — install all dependencies
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install system deps for pyarrow and matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv and resolve dependencies from the project lockfile
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock ./
RUN uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.lock \
    && pip install --no-cache-dir --prefix=/install -r requirements.lock

# ─────────────────────────────────────────────────────────────
# Stage 2: Runtime — lean production image
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Install supercronic for cron scheduling
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && curl -fsSL https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-arm64 -o /usr/local/bin/supercronic \
    && chmod +x /usr/local/bin/supercronic \
    && apt-get remove -y curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy source code
COPY src/ ./src/

# Persistent volumes:
#   /app/.data_cache  — Parquet cache & SQLite paper trading DB & friction.json
#   /app/logs         — Daily run logs
VOLUME ["/app/.data_cache", "/app/logs"]

# Environment variables with safe defaults.
# Override these at runtime via: docker run -e SMTP_PASS=xxx ...
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SMTP_HOST="smtp.gmail.com" \
    SMTP_PORT="587" \
    SMTP_USER="" \
    SMTP_PASS="" \
    NOTIFY_EMAIL="" \
    TZ="Asia/Tokyo"

# Default command: show help
CMD ["python3", "-m", "src.paper.bot", "--help"]

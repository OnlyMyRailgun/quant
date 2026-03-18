# ─────────────────────────────────────────────────────────────
# Stage 1: Builder — install all dependencies
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system deps for pyarrow and matplotlib
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ─────────────────────────────────────────────────────────────
# Stage 2: Runtime — lean production image
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

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
CMD ["python3", "src/paper/bot.py", "--help"]

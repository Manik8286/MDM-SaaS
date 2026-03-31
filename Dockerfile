# Stage 1: builder — install all Python dependencies into /install
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Install dependencies into an isolated prefix so we can copy them cleanly
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: runtime — lean image with only what is needed to run
FROM python:3.12-slim AS runtime

# System packages needed at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssl \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root user
RUN groupadd --gid 1000 app \
    && useradd --uid 1000 --gid 1000 --no-create-home --shell /sbin/nologin app

WORKDIR /app

# Copy application source and config, then fix ownership in one layer
COPY app/ app/
COPY scripts/entrypoint.sh scripts/entrypoint.sh
COPY alembic.ini .
RUN chmod +x scripts/entrypoint.sh \
    && chown -R app:app /app

# Switch to non-root user
USER app

EXPOSE 8000

ENTRYPOINT ["/app/scripts/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

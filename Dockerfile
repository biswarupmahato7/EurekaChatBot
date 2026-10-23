# =============================================================================
# Eureka RAG Chatbot — Production Backend Dockerfile
# =============================================================================
# Python 3.11 slim image for minimal attack surface
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment and install python dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# Pre-download and cache embedding model weights in build stage
ENV HF_HOME=/opt/hf_cache
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# ── Runtime Stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install runtime utilities (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -d /app appuser

# Copy virtual environment and model cache from builder
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf_cache /opt/hf_cache

# Strict memory and thread-pool limits to fit within 512MB RAM free-tier ceilings
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    HF_HOME=/opt/hf_cache \
    MALLOC_ARENA_MAX=2 \
    MALLOC_TRIM_THRESHOLD_=100000 \
    PYTHONMALLOC=malloc \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    VECLIB_MAXIMUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    WEB_CONCURRENCY=1


# Create required persistent data directories with non-root ownership
RUN mkdir -p /app/data/vectorstore \
             /app/data/raw \
             /app/data/processed \
             /app/data/reports \
             /app/data/backups \
             /app/data/checkpoints && \
    chown -R appuser:appgroup /app/data

# Copy application source code and data assets
COPY backend/ /app/backend/
COPY crawler/ /app/crawler/
COPY scripts/ /app/scripts/
COPY deployment/entrypoint.sh /app/entrypoint.sh
COPY data/processed/ /app/data/processed/
COPY data/vectorstore/ /app/data/vectorstore/

# Ensure non-root ownership and execution permissions
RUN chmod +x /app/entrypoint.sh && \
    chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser:appgroup

# Expose FastAPI port
EXPOSE 8000

# Healthcheck targeting readiness probe (checks ChromaDB & model compatibility)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:${PORT:-8000}/health/ready || exit 1

# Configure bootstrap entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Launch production server with Uvicorn (uses WEB_CONCURRENCY=1 to prevent OOM on 512MB RAM)
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1} --proxy-headers --forwarded-allow-ips '*'"]


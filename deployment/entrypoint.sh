#!/bin/sh
set -e

# =============================================================================
# Eureka RAG Chatbot — Container Entrypoint & Volume Bootstrap
# =============================================================================

# Verify or bootstrap ChromaDB vector index in persistent storage
if [ ! -f "/app/data/vectorstore/chroma.sqlite3" ]; then
    echo "[Bootstrap] ChromaDB vector store not found at /app/data/vectorstore."
    if [ -f "/app/data/processed/eureka_website_chunks.json" ]; then
        echo "[Bootstrap] Found processed chunks dataset. Initializing vector index into persistent volume..."
        python -m scripts.build_index || echo "[Warning] Automatic index build failed. Check logs."
    else
        echo "[Bootstrap] No processed chunks found at /app/data/processed/eureka_website_chunks.json."
    fi
else
    echo "[Bootstrap] ChromaDB vector store verified at /app/data/vectorstore."
fi

# Hand over to CMD (Uvicorn server)
exec "$@"

# Backend — `backend/`

## Responsibility

This directory will contain the **FastAPI backend service** for the Eureka RAG Chatbot, implemented in **Phase C**.

The backend is the **only** component permitted to access the vector store (ChromaDB) and the Groq LLM API. The frontend widget communicates exclusively through the HTTP API exposed by this service — never directly to Groq or ChromaDB.

## Current status

**Phase 0 — Dependency stub only.** No backend implementation exists yet.

The dependency manifest (`requirements.txt`) is declared so that the technology stack is documented, but the backend stack is **not installed** during Phase 0. Installation begins in Phase B (embeddings) and Phase C (FastAPI + Groq).

## Intended structure (Phase C onwards)

```text
backend/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI application factory and routes
│   ├── config.py           # Validated Pydantic settings (env vars)
│   ├── logging_config.py   # Structured logging setup
│   ├── api/                # Request/response schemas and endpoint handlers
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   ├── chat.py         # POST /api/v1/chat
│   │   └── health.py       # GET /health/live, GET /health/ready
│   ├── rag/                # Scope checks, retrieval, prompt construction, citations
│   │   └── __init__.py
│   ├── llm/                # Groq adapter and provider error mapping
│   │   └── __init__.py
│   ├── embeddings/         # Embedding model wrapper (load at startup)
│   │   └── __init__.py
│   └── vectorstore/        # ChromaDB adapter implementing the storage interface
│       └── __init__.py
├── tests/                  # Backend unit and integration tests (Phase C)
│   └── __init__.py
├── requirements.txt
└── README.md
```

## API endpoints (Phase C target)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health/live` | Liveness — is the process running? |
| `GET` | `/health/ready` | Readiness — are vector store and config available? |
| `POST` | `/api/v1/chat` | Main question-answering endpoint |
| `POST` | `/api/v1/feedback` | Optional thumbs-up/down feedback (if approved) |

See `docs/architecture.md` §6.2 for the full request/response contract.

## Installation (Phase B/C)

```powershell
# Windows PowerShell — activate your venv first
pip install -r backend/requirements.txt
```

## Security requirements

- `GROQ_API_KEY` must **never** appear in client-side code, logs, Git history, or the handoff ZIP.
- The vector store must be accessible only by the backend process.
- CORS must be configured for the exact production frontend origin (see `.env.example` `ALLOWED_ORIGINS`).

## What belongs here

- FastAPI application code under `app/`.
- Backend unit and integration tests under `tests/`.
- Backend-specific dependency declarations in `requirements.txt`.

## What does NOT belong here

- Crawler source or scripts — those are in `crawler/`.
- Frontend widget code — that is in `frontend/` (Phase D) or `frontend-integration/`.
- Raw or processed JSON datasets — those are generated into `data/`.

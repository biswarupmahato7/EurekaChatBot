# Eureka RAG Chatbot — Ask Eureka AI

**Project:** Eureka Solutions — Ask Eureka AI  
**Website:** <https://eurekasolutions.in/Eureka2026/>  
**Current phase:** Phase 0 — Repository Bootstrap  
**Python:** 3.11 or newer required

> **Phase 0 scope notice:** The actual crawler, backend API, vector index, and frontend widget will be implemented in Phases A–F. This repository currently contains the clean, reproducible foundation: directory structure, dependency declarations, configuration template, documentation, and a passing smoke test.

---

## 1. Project purpose

Ask Eureka AI is a website chatbot that answers visitors' questions using traceable information retrieved from the approved Eureka Solutions website content. Relevant source passages are retrieved from a vector index and used to ground answers generated through Groq's API. Source links are returned alongside every answer.

---

## 2. Repository organization

```text
eureka-rag-chatbot/          ← project root (this workspace)
├── crawler/                 # Phase A — web crawler and data pipeline
│   ├── tests/               # Crawler tests (smoke test runs now)
│   ├── __init__.py
│   ├── requirements.txt     # Crawler-only dependencies (no API keys needed)
│   └── README.md
│
├── backend/                 # Phase B/C — FastAPI service, RAG, Groq integration
│   ├── requirements.txt     # Backend dependency stub (install in Phase B/C)
│   └── README.md
│
├── data/                    # Generated data (excluded from Git except .gitkeep)
│   ├── raw/                 # Crawled JSON output (Phase A)
│   ├── processed/           # Chunked JSON output (Phase A)
│   ├── reports/             # Validation and crawl reports (Phase A)
│   ├── checkpoints/         # Crawler run checkpoints (Phase A)
│   └── vectorstore/         # ChromaDB persistent index (Phase B)
│
├── docs/                    # Project documentation
│   ├── problamStatement.md  # Full product and technical specification (v2.0)
│   ├── architecture.md      # System architecture document (v2.0)
│   └── implementation-plan.md  # Phase-by-phase implementation plan (v2.0)
│
├── tests/                   # Top-level integration tests (future phases)
│   └── README.md
│
├── frontend-integration/    # API contract and frontend integration docs
│   └── README.md
│
├── .env.example             # Safe configuration template — NEVER commit .env
├── .gitignore               # Protects secrets, caches, generated data
├── pytest.ini               # pytest discovery configuration
├── requirements-dev.txt     # Development and testing tools
└── README.md                # ← you are here
```

> **Note on `docs/problamStatement.md`:** The filename contains a typo from the original document (`problamStatement.md` instead of `problemStatement.md`). The file is preserved exactly as named to avoid breaking any existing references. Internally it is the authoritative problem statement document.

---

## 3. Supported Python version

**Python 3.11 or newer** (project requirement per problem statement §7.1 and architecture §4.1).

Check your version:

```powershell
# Windows PowerShell
python --version
```

```bash
# Linux / macOS
python3 --version
```

---

## 4. Environment setup

### Step 1 — Create and activate a virtual environment

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\activate
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### Step 2 — Install development dependencies

```powershell
pip install -r requirements-dev.txt
```

### Step 3 — Install crawler dependencies

```powershell
pip install -r crawler/requirements.txt
```

### Step 4 — Configure local environment

```powershell
# Windows PowerShell
copy .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

Edit `.env` to set real values. **Never commit `.env` to Git** — it is protected by `.gitignore`.

---

## 5. Running the crawler smoke tests (Phase 0 — works now)

From the repository root, with the virtual environment activated:

```powershell
python -m pytest crawler/tests -v
```

Expected output: all tests pass. The smoke tests verify:

- Python version ≥ 3.11
- The `crawler` package is importable
- All crawler dependencies (`requests`, `beautifulsoup4`, `pydantic`, `tiktoken`, `python-dotenv`) are installed
- Standard-library URL utilities are available
- URL normalization and scope enforcement logic works correctly
- `tiktoken` loads and counts tokens correctly
- Pydantic v2 model validation works

These tests require **no network access**, **no API keys**, and **no running backend**.

---

## 6. Phase-by-phase implementation overview

| Phase | Name | Status |
|-------|------|--------|
| **0** | Repository Bootstrap | ✅ **Complete** |
| **A** | Website Data Pipeline (crawler, chunker, validator) | 🔲 Not started |
| **B** | Retrieval Foundation (embeddings, ChromaDB, index) | 🔲 Not started |
| **C** | Backend Chatbot (FastAPI, Groq, RAG pipeline) | 🔲 Not started |
| **D** | Frontend Widget (Ask Eureka AI chat widget) | 🔲 Not started |
| **E** | Integration and Evaluation (E2E tests, quality) | 🔲 Not started |
| **F** | Deployment and Handoff (production, runbooks) | 🔲 Not started |

---

## 7. Future phase commands (not yet implemented)

These commands will be available after Phase A is implemented:

```powershell
# Phase A — Crawl and process
python scripts/crawl_website.py --max-pages 200
python scripts/create_chunks.py --target-tokens 500 --overlap-tokens 75
python scripts/run_pipeline.py --mode full
python scripts/run_pipeline.py --mode incremental
python scripts/validate_data.py
```

```powershell
# Phase B — Build vector index
python scripts/build_index.py

# Phase C — Run the backend API
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

Do not run these commands until the respective phases are implemented.

---

## 8. Configuration and API-key security

- Copy `.env.example` → `.env` for local configuration.
- **Never commit `.env`** — it is excluded by `.gitignore`.
- The `GROQ_API_KEY` is a backend-only secret. It must **never** appear in:
  - Frontend/client-side code or public environment variables
  - Application logs or error responses
  - Git history or the handoff ZIP
- The crawler and its tests require **no API keys**. Configure and run them independently of the backend.
- See `.env.example` for all configuration options with documentation.

---

## 9. Project documentation

| Document | Description |
|----------|-------------|
| [problamStatement.md](docs/problamStatement.md) | Full product and technical specification (v2.0) |
| [architecture.md](docs/architecture.md) | System architecture — components, data flow, APIs (v2.0) |
| [implementation-plan.md](docs/implementation-plan.md) | Phase-by-phase implementation plan (v2.0) |

---

## 10. Contributing

- Follow the phase boundaries defined in `docs/implementation-plan.md`.
- Do not implement later phases prematurely.
- Never commit real API keys, `.env`, populated vector-store files, or live crawl data.
- All tests must pass without network access or API keys.
- Run `python -m pytest crawler/tests -v` before submitting changes to the crawler.

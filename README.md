# Eureka RAG Chatbot — Ask Eureka AI

**Project:** Eureka Solutions — Ask Eureka AI  
**Website:** <https://eurekasolutions.in/Eureka2026/>  
**Status:** **Phase F Complete (Production Staging Verified, Awaiting Production Release Gate)**  
**Python:** 3.11 or newer required  
**Node.js:** 20.x or 22.x LTS required  

---

## 1. Project Purpose & Architecture

**Ask Eureka AI** is an enterprise-grade website chatbot designed to answer visitors' inquiries using grounded, traceable information retrieved from the approved Eureka Solutions website content.

Answers are strictly grounded in a persistent ChromaDB vector store (3,796 chunks across 102 validated website pages) using dense semantic search (`all-MiniLM-L6-v2`) and generated through OpenAI's official API (`gpt-4o-mini`).

```
[ Visitor Browser ] ──► [ Edge Nginx / TLS ] ──► [ React 19 Widget ]
                                                        │
                                                        ▼ POST /api/v1/chat
                                              [ FastAPI Backend ]
                                                        │
                      ┌─────────────────────────────────┴─────────────────────────────────┐
                      ▼                                                                   ▼
       [ Smart Conversation Router ]                                        [ Semantic Retriever ]
       - Intercepts trivia, food, sports (out_of_scope)                      - ChromaDB (3,796 chunks)
       - Handles profanity/insults calmly                                   - Cosine relevance threshold
       - Disambiguation & quick-reply chips                                 - Source diversity cap
                      │                                                                   │
                      └─────────────────────────────────┬─────────────────────────────────┘
                                                        │
                                                        ▼
                                              [ OpenAI Client ]
                                              - Model: gpt-4o-mini
                                              - Responses API / Chat Completions
                                              - Bounded retries (30s timeout)
                                                        │
                                                        ▼
                                              [ Grounded Answer ]
                                              - Verified contact (info@eurekasolutions.in)
                                              - Sources hidden in UI
```

---

## 2. Repository Layout

```text
eureka-rag-chatbot/
├── backend/                 # FastAPI service, RAG orchestration, OpenAI client, storage
│   ├── app/                 # FastAPI application, routers, schemas, middleware, services
│   ├── embeddings/          # SentenceTransformer & mock embedder adapters
│   ├── indexing/            # Batch indexing engine, manifest tracking
│   ├── retrieval/           # Dense semantic retriever, deduplication
│   ├── vectorstore/         # ChromaDB persistent store adapter
│   ├── tests/               # Backend unit and integration tests (88 tests)
│   └── requirements.txt     # Production backend dependencies
│
├── crawler/                 # Phase A website crawler and data processing pipeline
│   ├── cli/                 # CLI entrypoints (crawl, chunk, validate, package)
│   ├── tests/               # Offline fixture-based crawler tests (143 tests)
│   └── requirements.txt     # Crawler dependencies
│
├── frontend/                # Phase D/E React 19 + TypeScript + Vite chat widget
│   ├── src/                 # Widget components, API client, hooks, styles
│   ├── dist/                # Production distribution bundle
│   └── package.json         # Frontend dependencies and test scripts
│
├── deployment/              # Phase F deployment infrastructure
│   ├── Dockerfile           # Multi-stage backend container (non-root appuser)
│   ├── Dockerfile.frontend  # Multi-stage frontend container (Nginx)
│   ├── docker-compose.yml   # Staging & production multi-service stack
│   ├── nginx/               # Production Nginx reverse-proxy & TLS configs
│   └── systemd/             # Linux systemd service unit file
│
├── data/                    # Generated datasets and persistent storage
│   ├── raw/                 # eureka_website_data.json (102 pages)
│   ├── processed/           # eureka_website_chunks.json (3,796 chunks)
│   ├── vectorstore/         # ChromaDB SQLite & HNSW index files
│   ├── reports/             # Crawl and indexing validation reports
│   └── backups/             # Timestamped cryptographic backups
│
├── docs/                    # Complete project documentation
│   ├── DEPLOYMENT.md        # Staging & production deployment guide
│   ├── OPERATIONS_RUNBOOK.md# Operations, KB refresh, backups, incident runbooks
│   ├── FINAL_HANDOFF.md     # Final integration and handoff note
│   ├── TEST_REPORT.md       # Comprehensive evaluation and security report
│   ├── API_CONTRACT.md      # OpenAPI specification and error schema contract
│   └── architecture.md      # Detailed system architecture document
│
├── scripts/                 # Maintenance, backup, and release automation
│   ├── backup_manager.py    # Backup snapshot and isolated restore test utility
│   ├── package_source.py    # Clean source archive builder
│   ├── build_index.py       # Safe batch index builder
│   └── export_openapi.py    # OpenAPI JSON schema exporter
│
├── .env.example             # Safe environment configuration template
├── eureka-rag-source.tar.gz # Verified source code package
└── eureka-rag-data.zip      # Verified Phase A data package
```

---

## 3. Quick Start & Local Setup

### Step 1 — Python Virtual Environment

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend/requirements.txt
pip install -r requirements-dev.txt
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r requirements-dev.txt
```

### Step 2 — Configure Environment Variables

```powershell
copy .env.example .env
```
Fill in your `OPENAI_API_KEY` in `.env`.

### Step 3 — Launch the Backend Service

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```
- Verify health: `http://127.0.0.1:8000/health/ready` (Reports collection: `eureka_website_chunks`, count: 3796).

### Step 4 — Launch the Frontend Widget

```bash
cd frontend
npm ci
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 4. Automated Testing (401 Tests, 100% Pass Rate)

### Run Backend, Crawler, and Edge-Case Test Suite (337 Tests)

```powershell
.\.venv\Scripts\python.exe -m pytest --tb=short -q
```
*All 337 tests pass in ~2 minutes with zero network calls and zero mock leaks.*

### Run Frontend Vitest Suite (64 Tests)

```bash
cd frontend
npm test
```
*All 64 component, accessibility, markdown, and quick-reply tests pass.*

---

## 5. Maintenance & Operational Commands

All data maintenance tasks run **outside user requests** via dedicated CLI scripts:

### Backup & Isolated Restore Verification
```powershell
# Create a timestamped backup with SHA-256 manifests
.\.venv\Scripts\python.exe scripts/backup_manager.py create --tag release

# Execute isolated restore test in a separate sandbox directory
.\.venv\Scripts\python.exe scripts/backup_manager.py restore-test
```

### Safe Knowledge-Base Refresh Workflow
```powershell
# 1. Incremental Crawl (requires internet)
.\.venv\Scripts\python.exe -m crawler.cli.crawl_website --incremental

# 2. Validate Raw JSON (100% offline)
.\.venv\Scripts\python.exe -m crawler.cli.validate_data --raw-only

# 3. Regenerate Chunks (100% offline)
.\.venv\Scripts\python.exe -m crawler.cli.create_chunks

# 4. Validate Chunks (100% offline)
.\.venv\Scripts\python.exe -m crawler.cli.validate_data --chunks-only

# 5. Safe Rebuild (pre-computes embeddings before resetting index)
.\.venv\Scripts\python.exe scripts/build_index.py --rebuild

# 6. Evaluate Retrieval Recall
.\.venv\Scripts\python.exe -m backend.evaluation.evaluate_retrieval
```

### Create Distribution Packages
```powershell
# Create and verify clean source archive (eureka-rag-source.tar.gz)
.\.venv\Scripts\python.exe scripts/package_source.py

# Create and verify Phase A data package (eureka-rag-data.zip)
.\.venv\Scripts\python.exe -m crawler.cli.package_data
```

---

## 6. Deployment Environments

| Environment | Host Architecture | Documentation Reference |
|---|---|---|
| **Local Staging** | Local Uvicorn (port 8000) + Vite (port 5173) | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#4-launching-the-backend-service) |
| **Docker Compose** | Multi-container stack (Nginx TLS + Backend + Frontend) | [deployment/docker-compose.yml](deployment/docker-compose.yml) |
| **Linux Host (VM)** | Systemd process manager + Nginx reverse proxy | [deployment/systemd/eureka-backend.service](deployment/systemd/eureka-backend.service) |

For complete operations, disaster recovery, and incident runbooks, see [docs/OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md).

---

## 7. Security & Privacy Safeguards

- **Zero Secret Commits:** Git ignores `.env`, keys, virtual environments, and SQLite databases.
- **Privacy First:** User query texts are masked from logs at `INFO` level (`LOG_QUERY_TEXT=false`).
- **Prompt Injection Defense:** Untrusted web text is isolated in `<retrieved_context>` XML tags; system override instructions are refused or neutralized.
- **SSRF Crawler Guards:** The crawler rejects loopback, RFC 1918 private IPs, and out-of-scope HTTP redirects.
- **CORS Protection:** Requests are restricted to exact approved origins (`https://eurekasolutions.in`).
- **Grounded Responses:** Unverified claims and unapproved external links are stripped; absence of facts triggers polite abstention (`insufficient_evidence`).
- **Verified Contact Channel:** Directs users only to verified email `info@eurekasolutions.in` in Mumbai.

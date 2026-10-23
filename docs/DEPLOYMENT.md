# Ask Eureka AI — Production & Staging Deployment Guide

**Document:** `docs/DEPLOYMENT.md`  
**Project:** Eureka Solutions — Ask Eureka AI RAG Chatbot  
**Target Website:** `https://eurekasolutions.in/Eureka2026/`  
**Target Deployment Capacity:** ~50 sessions/day initial operational estimate  
**Primary LLM Provider:** OpenAI (`gpt-4o-mini`, Responses API / Chat Completions)  
**Vector Database:** ChromaDB Persistent Store (Collection: `eureka_website_chunks`)  
**Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)  
**Version:** 1.0.0 (Phase F Release)  

---

## 1. Supported Architecture & Prerequisites

The Ask Eureka AI chatbot uses a decoupled RAG architecture designed for reliability, strict data grounding, and high interactive responsiveness.

```
                           [ Internet / Browser Visitors ]
                                         │
                                         ▼ HTTPS (443)
                         ┌───────────────────────────────┐
                         │   Edge Nginx Reverse Proxy    │
                         │   - TLS Termination (HTTPS)   │
                         │   - Sliding-Window Rate Limit │
                         │   - Exact CORS Header Guard   │
                         │   - Static Asset Caching      │
                         └───────┬───────────────┬───────┘
                                 │               │
                     /api, /health               │ / (Root & Assets)
                                 │               │
                                 ▼               ▼
                   ┌───────────────────┐   ┌───────────────────┐
                   │  FastAPI Backend  │   │  Frontend Widget  │
                   │  (Python 3.11+)   │   │  (React 19 / Vite)│
                   │  Port 8000        │   │  Port 80          │
                   └─────────┬─────────┘   └───────────────────┘
                             │
            ┌────────────────┴────────────────┐
            ▼                                 ▼
┌─────────────────────────┐       ┌─────────────────────────┐
│ Persistent ChromaDB     │       │ OpenAI Cloud API        │
│ Volume: data/vectorstore│       │ Model: gpt-4o-mini      │
│ 3,796 Chunks / 102 Pages│       │ Strict Responses API    │
└─────────────────────────┘       └─────────────────────────┘
```

### System Requirements

| Component | Minimum Specification | Recommended Production Specification |
|---|---|---|
| **Operating System** | Ubuntu 22.04 LTS / Debian 12 / Windows Server 2022 | Ubuntu 24.04 LTS or Container Host |
| **CPU Architecture** | x86_64 or ARM64 (2 cores) | 4 vCPUs |
| **RAM** | 4 GB | 8 GB (SentenceTransformers + ChromaDB in memory) |
| **Disk Storage** | 20 GB SSD | 50 GB NVMe SSD (data, vectorstore, backups) |
| **Python** | 3.11.5 or newer | 3.11.9+ |
| **Node.js** | 20.x LTS or 22.x LTS | 20.x LTS |
| **Reverse Proxy** | Nginx 1.22+ or Cloudflare / AWS ALB | Nginx 1.24+ with TLS 1.3 |

---

## 2. Runtime Dependencies & Installation

### Option A: Python Virtual Environment (Bare Metal / VM)

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
pip install -r requirements-dev.txt
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
pip install -r requirements-dev.txt
```

### Option B: Frontend Node Dependencies

```bash
cd frontend
npm ci
```

---

## 3. Environment Variable Reference

The application reads configuration from `.env` at the project root using validated Pydantic settings. Copy `.env.example` to start:

```bash
cp .env.example .env
```

### Complete Variable Reference

| Variable | Type | Default | Description |
|---|---|---|---|
| `APP_ENV` | `str` | `development` | `development`, `staging`, or `production`. Disables `/docs` in production. |
| `APP_HOST` | `str` | `0.0.0.0` | Bind IP address for FastAPI server. |
| `APP_PORT` | `int` | `8000` | Port for FastAPI server. |
| `API_BASE_PATH` | `str` | `/api/v1` | URL route prefix. |
| `ALLOWED_ORIGINS` | `list[str]` | `http://localhost:3000,http://localhost:5173,https://eurekasolutions.in` | Exact allowed CORS origins without trailing slashes. |
| `ENABLE_DOCS` | `bool` | `false` | Enable interactive Swagger UI / ReDoc. Defaults to `false` in production. |
| `TRUSTED_PROXIES` | `list[str]` | `127.0.0.1` | Proxy IPs trusted for client IP extraction (`X-Forwarded-For`). |
| `LOG_QUERY_TEXT` | `bool` | `false` | Privacy flag. If `false`, user prompts are never logged at `INFO` level. |
| `MAX_MESSAGE_CHARACTERS` | `int` | `2000` | Maximum message character limit per turn (bounds: 1–2000). |
| `RATE_LIMIT_PER_MINUTE` | `int` | `60` | Max requests per client IP per minute before returning HTTP 429. |
| `LLM_PROVIDER` | `str` | `openai` | Active provider (`openai` or `groq`). |
| `OPENAI_API_KEY` | `str` | *(secret)* | Secret API key for OpenAI Cloud API. |
| `OPENAI_MODEL` | `str` | `gpt-4o-mini` | Model ID for OpenAI grounded chat generation. |
| `OPENAI_TIMEOUT_SECONDS` | `float` | `30.0` | Timeout per OpenAI API call. |
| `OPENAI_MAX_RETRIES` | `int` | `2` | Bounded retry attempts with exponential backoff for transient errors. |
| `OPENAI_MAX_OUTPUT_TOKENS` | `int` | `1024` | Ceiling for tokens in LLM generation. |
| `CHROMA_PERSIST_DIRECTORY` | `str` | `./data/vectorstore` | Persistent directory for ChromaDB vector index. |
| `CHROMA_COLLECTION` | `str` | `eureka_website_chunks` | Name of ChromaDB collection. |
| `EMBEDDING_MODEL` | `str` | `sentence-transformers/all-MiniLM-L6-v2` | Dense sentence embedding model. |
| `EMBEDDING_DIMENSION` | `int` | `384` | Embedding dimensionality (must match model). |
| `TOP_K` | `int` | `6` | Top-k chunks retrieved per user question. |
| `EVIDENCE_MIN_SCORE` | `float` | `0.45` | Minimum cosine relevance score for sufficiency check. |
| `MAX_CITATIONS` | `int` | `5` | Maximum citation links returned in API response. |
| `CANONICAL_BASE_URL` | `str` | `https://eurekasolutions.in/Eureka2026/` | Canonical base URL for verified citations. |

---

## 4. Launching the Backend Service

### Local Development / Testing

```powershell
# Windows PowerShell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

```bash
# Linux
source .venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

### Verification Probes

```bash
# 1. Liveness check
curl -f http://127.0.0.1:8000/health/live
# Expected: {"status": "ok"}

# 2. Readiness check (checks ChromaDB and model compatibility)
curl -f http://127.0.0.1:8000/health/ready
# Expected: {"status": "ready", "vector_store": "ok", "collection": "eureka_website_chunks", "chunks_count": 3796}
```

---

## 5. Building and Serving the Frontend Widget

### Step 1 — Configure Frontend Environment

In `frontend/`:
- Development: `frontend/.env.development` sets `VITE_EUREKA_API_BASE_URL=""` (requests route through Vite proxy).
- Production: `frontend/.env.production` sets `VITE_EUREKA_API_BASE_URL="https://api.eurekasolutions.in"`.

### Step 2 — Build Production Bundle

```bash
cd frontend
npm ci
npm run build
```

The production bundle will be emitted to `frontend/dist/`.

### Step 3 — Embedding the Widget into the Eureka Solutions Website

Include the compiled CSS and JS in the host website layout just before `</body>`:

```html
<!-- Eureka Chatbot Widget Mount -->
<div id="eureka-chat-root"></div>
<link rel="stylesheet" href="/assets/index-CotMEkT1.css" />
<script type="module" src="/assets/index-DHQSIDJH.js"></script>

<!-- Optional Runtime Configuration -->
<script>
  window.__EUREKA_CONFIG__ = {
    apiBaseUrl: "https://api.eurekasolutions.in"
  };
</script>
```


---

## 6. Reverse Proxy & HTTPS Configuration

Production deployments **must not** expose Uvicorn directly to the public internet. Deploy Nginx in front of Uvicorn to terminate TLS and forward requests.

### Key Nginx Directives (`deployment/nginx/nginx.conf`)

1. **Proxy Headers:**
   ```nginx
   proxy_set_header Host $host;
   proxy_set_header X-Real-IP $remote_addr;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   proxy_set_header X-Forwarded-Proto $scheme;
   proxy_set_header X-Request-ID $request_id;
   ```
2. **Rate Limiting:**
   ```nginx
   limit_req_zone $binary_remote_addr zone=api_rate_limit:10m rate=10r/s;
   limit_req zone=api_rate_limit burst=20 nodelay;
   ```
3. **Security Headers:**
   ```nginx
   add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
   add_header X-Content-Type-Options "nosniff" always;
   add_header X-Frame-Options "SAMEORIGIN" always;
   add_header Referrer-Policy "strict-origin-when-cross-origin" always;
   ```

### Obtaining SSL/TLS Certificates with Let's Encrypt (Certbot)

```bash
sudo apt update && sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d api.eurekasolutions.in -d chatbot.eurekasolutions.in
```

Certificates will be issued to `/etc/letsencrypt/live/api.eurekasolutions.in/`.

---

## 7. Persistent ChromaDB Storage

ChromaDB uses SQLite (`chroma.sqlite3`) and binary HNSW index files (`data_level0.bin`, `header.bin`) stored on local disk.

### Durability Requirements
- Do **not** place `data/vectorstore` in an ephemeral container filesystem.
- In Docker deployments, mount a persistent host volume:
  ```yaml
  volumes:
    - /var/data/eureka/vectorstore:/app/data/vectorstore:rw
  ```
- Ensure file permissions allow the `appuser` (UID 10001) to read and write to the directory.
- Verify persistence by restarting the container and checking `/health/ready` reports `chunks_count: 3796`.

---

## 8. Staging Deployment Procedure (Step-by-Step)

1. **Provision Staging VM / Container Host:**
   - Operating System: Ubuntu 22.04 LTS.
   - Configure DNS: Point `staging-api.eurekasolutions.in` to staging IP.
2. **Transfer Source Code & Verified Index:**
   ```bash
   git clone <repo-url> /opt/eureka-rag-chatbot
   cd /opt/eureka-rag-chatbot
   ```
3. **Copy Verified Persistent Index & Chunks:**
   - Transfer `data/vectorstore/` and `data/processed/eureka_website_chunks.json` from verified release package.
4. **Configure Staging Environment:**
   ```bash
   cp .env.example .env
   # Edit .env:
   # APP_ENV=staging
   # OPENAI_API_KEY=sk-...
   # ALLOWED_ORIGINS=https://staging-chat.eurekasolutions.in,https://eurekasolutions.in
   ```
5. **Start Staging Stack with Docker Compose:**
   ```bash
   docker compose -f deployment/docker-compose.yml up -d --build
   ```
6. **Verify Health Probes:**
   ```bash
   curl -f https://staging-api.eurekasolutions.in/health/live
   curl -f https://staging-api.eurekasolutions.in/health/ready
   ```
7. **Execute Staging Smoke Test:**
   ```bash
   curl -X POST https://staging-api.eurekasolutions.in/api/v1/chat \
     -H "Content-Type: application/json" \
     -H "Origin: https://eurekasolutions.in" \
     -d '{"message": "What ERP software does Eureka Solutions implement?"}'
   ```
   Verify HTTP 200, `status: "answered"`, valid citation links, and correlation `X-Request-ID`.

---

## 9. Production Deployment Procedure & Release Gate

> [!IMPORTANT]
> **Production Release Gate:** No deployment to production infrastructure may occur without explicit written authorization from the project owner.

### Pre-Deployment Checklist
- [x] All 401 automated tests passing (337 backend/crawler + 64 frontend).
- [x] Isolated backup restoration test executed and passing (`scripts/backup_manager.py restore-test`).
- [x] Clean source archive created and verified (`eureka-rag-source.tar.gz`).
- [x] Clean data package created and verified (`eureka-rag-data.zip`).
- [x] Zero API keys or secrets in version control or frontend bundles.
- [x] HTTPS enforced with valid TLS certificate.
- [x] `ALLOWED_ORIGINS` strictly restricted to `https://eurekasolutions.in`.
- [x] Owner approval obtained.

### Rollout Steps
1. Place edge proxy into maintenance mode or deploy behind blue/green load balancer.
2. Pull release tag / unpack `eureka-rag-source.tar.gz`.
3. Mount verified `data/vectorstore` persistent volume.
4. Set production `.env` with production OpenAI credentials.
5. Launch services:
   ```bash
   docker compose -f deployment/docker-compose.yml up -d
   ```
6. Verify `/health/ready` returns HTTP 200 with 3,796 records.
7. Switch traffic to new release.
8. Monitor logs and OpenAI usage metrics for 30 minutes.

---

## 10. Rollback Procedure

If a critical issue occurs after deployment:

1. **Revert Backend Container / Service:**
   ```bash
   docker compose -f deployment/docker-compose.yml stop backend
   # Re-point volume to previous verified backup:
   python scripts/backup_manager.py restore-test --backup data/backups/backup_previous_known_good
   docker compose -f deployment/docker-compose.yml up -d backend
   ```
2. **Revert Frontend Bundle:**
   Re-deploy previous `dist/` directory on Nginx server.
3. **Verify Restored Health:**
   ```bash
   curl -f https://api.eurekasolutions.in/health/ready
   ```

---

## 11. Maintenance Commands (Outside the Request Path)

All crawling, extraction, chunking, and reindexing tasks are maintenance operations and **must never run inside a user request**.

| Maintenance Task | Command | Preconditions |
|---|---|---|
| **Incremental Crawl** | `python -m crawler.cli.crawl_website --incremental` | Internet access to `eurekasolutions.in` |
| **Validate Raw JSON** | `python -m crawler.cli.validate_data --raw-only` | `data/raw/eureka_website_data.json` exists |
| **Generate Chunks** | `python -m crawler.cli.create_chunks` | Validated raw data |
| **Validate Chunks** | `python -m crawler.cli.validate_data --chunks-only` | `data/processed/eureka_website_chunks.json` exists |
| **Safe Index Rebuild** | `python -m scripts.build_index --rebuild` | Validated chunks; retains old index on failure |
| **Retrieval Evaluation** | `python -m backend.evaluation.evaluate_retrieval` | Built ChromaDB index |
| **Create Backup** | `python scripts/backup_manager.py create --tag manual` | Quiesces ChromaDB WAL |
| **Verify Restore** | `python scripts/backup_manager.py restore-test` | Tests in isolated sandbox |
| **Package Data ZIP** | `python -m crawler.cli.package_data` | Phase A deliverables |
| **Package Source Archive** | `python scripts/package_source.py` | Full repo (excludes secrets/caches) |

---

## 12. Troubleshooting Common Deployment Errors

### 1. HTTP 503 "Index Incompatible"
- **Cause:** `EMBEDDING_MODEL` or dimension in `.env` does not match `index_manifest.json`.
- **Fix:** Ensure `.env` specifies `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` and dimension `384`, or rebuild the index using `python scripts/build_index.py --rebuild`.

### 2. HTTP 403 Forbidden / CORS Rejection
- **Cause:** Request `Origin` header is not present in `ALLOWED_ORIGINS`.
- **Fix:** Add the host domain (e.g. `https://eurekasolutions.in`) to `ALLOWED_ORIGINS` in `.env` (no trailing slashes).

### 3. HTTP 429 Too Many Requests
- **Cause:** Client IP exceeded `RATE_LIMIT_PER_MINUTE=60`.
- **Fix:** Wait for the sliding window to reset (check `Retry-After` header) or tune `RATE_LIMIT_PER_MINUTE` in `.env`.

### 4. HTTP 503 "LLM Provider Unavailable"
- **Cause:** OpenAI API key is missing, expired, or network egress to `api.openai.com` is blocked.
- **Fix:** Check `OPENAI_API_KEY` in `.env`, verify account credit/quota in OpenAI dashboard, and test outgoing HTTPS egress.

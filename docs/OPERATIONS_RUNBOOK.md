# Ask Eureka AI — Operations Runbook

**Document:** `docs/OPERATIONS_RUNBOOK.md`  
**Target Environment:** Staging & Production  
**Component:** Eureka Solutions — Ask Eureka AI RAG System  
**Version:** 1.0.0 (Phase F Release)  

---

## 1. Overview & Operational Principles

This runbook provides actionable, step-by-step procedures for operating, monitoring, troubleshooting, refreshing, and recovering the **Ask Eureka AI** chatbot service.

### Operational Golden Rules
1. **Never perform maintenance inside user requests:** Crawling, chunking, embedding generation, and index rebuilds must run strictly as offline maintenance jobs.
2. **Never expose secrets:** Never print `OPENAI_API_KEY`, tokens, or database passwords to stdout, logs, Slack, or tickets.
3. **Always verify before replacing:** New crawl datasets and vector indexes must be cryptographically and semantically verified before swapping out active production data.
4. **Preserve last-known-good state:** Never delete the current working index or data files until candidate data has passed automated validation.

---

## 2. Application Lifecycle Runbook

### 2.1 Start Service

#### Systemd (Linux VM)
```bash
sudo systemctl start eureka-backend
```
- **Verification:** `sudo systemctl status eureka-backend`
- **Expected:** `Active: active (running)`

#### Docker Compose
```bash
docker compose -f deployment/docker-compose.yml up -d
```
- **Verification:** `docker compose -f deployment/docker-compose.yml ps`
- **Expected:** `backend (healthy)`, `frontend (Up)`, `reverse-proxy (Up)`

#### Windows PowerShell (Development / Staging)
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 2
```

---

### 2.2 Stop Service

#### Systemd
```bash
sudo systemctl stop eureka-backend
```

#### Docker Compose
```bash
docker compose -f deployment/docker-compose.yml down
```

---

### 2.3 Graceful Restart

#### Systemd
```bash
sudo systemctl restart eureka-backend
```

#### Docker Compose
```bash
docker compose -f deployment/docker-compose.yml restart backend
```
- **Verification:** Check health probes immediately after restart:
  ```bash
  curl -f http://127.0.0.1:8000/health/live
  curl -f http://127.0.0.1:8000/health/ready
  ```

---

### 2.4 Health & Readiness Checks

| Probe URL | Method | Purpose | Healthy Response | Action if Failing |
|---|---|---|---|---|
| `/health/live` | `GET` | Process liveness | `{"status": "ok"}` (HTTP 200) | Restart process / inspect out-of-memory crashes. |
| `/health/ready` | `GET` | Dependency readiness | `{"status": "ready", "vector_store": "ok", "collection": "...", "chunks_count": 3796}` | Inspect ChromaDB storage or model compatibility. |

---

### 2.5 Log Inspection & Log Rotation

#### Viewing Logs
```bash
# Systemd journal
sudo journalctl -u eureka-backend -n 100 -f

# Docker container logs
docker compose -f deployment/docker-compose.yml logs -f --tail=100 backend

# Reverse proxy access/error logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

#### Log Hygiene & Privacy
- By default, `LOG_QUERY_TEXT=false` in `.env`.
- Service logs record only `request_id`, client IP, status code, chunk counts, and latency.
- Never set `LOG_LEVEL=DEBUG` in production unless actively diagnosing a non-sensitive issue, and revert to `INFO` immediately after.

#### Logrotate Configuration (`/etc/logrotate.d/eureka-rag`)
```conf
/var/log/nginx/*.log /opt/eureka-rag-chatbot/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 eureka eureka
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 $(cat /var/run/nginx.pid)
    endscript
}
```

---

## 3. LLM Provider Operations (OpenAI)

### 3.1 Verify Configured Provider & Model (Without Leaking Secrets)

Run this non-destructive check:
```bash
python -c "
from backend.app.config import get_app_settings
s = get_app_settings()
print(f'Provider: {s.llm_provider}')
print(f'Model: {s.openai_model}')
print(f'API Key Present: {bool(s.openai_api_key)}')
print(f'API Key Prefix: {s.openai_api_key[:7] + \"...\" if s.openai_api_key else \"None\"}')
"
```
- **Expected Output:**
  ```text
  Provider: openai
  Model: gpt-4o-mini
  API Key Present: True
  API Key Prefix: sk-proj...
  ```

---

### 3.2 Rotate OpenAI API Keys

1. **Generate New Key:**
   - Log into [OpenAI Platform Dashboard](https://platform.openai.com/api-keys).
   - Create a restricted or standard secret key named `eureka-chatbot-prod-<date>`.
2. **Update Environment File:**
   ```bash
   # On deployment host
   sudo nano /opt/eureka-rag-chatbot/.env
   # Update: OPENAI_API_KEY=sk-...new-key...
   ```
3. **Gracefully Restart Backend:**
   ```bash
   sudo systemctl restart eureka-backend
   # Or: docker compose -f deployment/docker-compose.yml restart backend
   ```
4. **Execute Verification Smoke Query:**
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "What services does Eureka Solutions offer?"}'
   ```
   - **Verification:** Ensure HTTP 200 and `status: "answered"`.
5. **Revoke Old Key:**
   - Once verified, delete the retired key in the OpenAI dashboard.

---

### 3.3 Diagnosing Rate Limit (429) & Quota Issues

- **Symptoms:** Chat API returns HTTP 503 with user message *"Our assistant is experiencing high inquiry volume. Please try again in a few moments."*
- **Diagnostic Steps:**
  1. Inspect error code in backend log: `grep -i "openai" /var/log/syslog | grep "429"`
  2. Check OpenAI usage & billing status at `https://platform.openai.com/usage`.
  3. Verify whether rate limit is TPM (tokens per minute) or RPM (requests per minute).
  4. With `gpt-4o-mini`, standard tier limits are 500–5,000 RPM and 200,000–2,000,000 TPM, which easily supports the target 50 sessions/day.
  5. If quota exhausted: add credit balance in billing settings.

---

## 4. Knowledge-Base Refresh & Safe Reindex Runbook

When the Eureka Solutions website content is updated, follow this safe progression:

```
[ Crawl (Incremental) ] ──► [ Validate Raw JSON ] ──► [ Generate Chunks ] ──►
        │
        ▼
[ Validate Chunks ] ──► [ Build Candidate Index ] ──► [ Evaluate Recall ] ──► [ Swap & Verify ]
```

### Step 1: Execute Incremental Crawl
```bash
python -m crawler.cli.crawl_website --incremental
```
- **Preconditions:** Network egress to `https://eurekasolutions.in/Eureka2026/`.
- **Expected:** Emits `data/reports/crawl_report_<uuid>.json` showing visited, updated, or skipped pages.

### Step 2: Validate Raw Dataset
```bash
python -m crawler.cli.validate_data --raw-only
```
- **Expected:** `Validation PASSED: 102 pages valid.`

### Step 3: Regenerate Chunks
```bash
python -m crawler.cli.create_chunks
```
- **Expected:** Emits updated `data/processed/eureka_website_chunks.json`.

### Step 4: Validate Processed Chunks
```bash
python -m crawler.cli.validate_data --chunks-only
```
- **Expected:** `Chunk Validation PASSED: 3,796 chunks valid.`

### Step 5: Safe Candidate Index Rebuild
```bash
python -m scripts.build_index --rebuild
```
> [!NOTE]
> The `IndexBuilder` engine pre-computes all embeddings into memory before resetting or modifying the active ChromaDB collection (`INDEX-012`). If embedding calculation fails midway, the existing production collection remains intact and untouched.

### Step 6: Evaluate Retrieval Recall
```bash
python -m backend.evaluation.evaluate_retrieval
```
- **Expected:** 100% HitRate@6, Recall@6 >= 0.95 across golden evaluation queries.

### Step 7: Create Backup of New State
```bash
python scripts/backup_manager.py create --tag post_kb_refresh
```

### Step 8: Hot Reload / Restart Service
```bash
docker compose -f deployment/docker-compose.yml restart backend
```
Verify `/health/ready` reports the updated record count.

---

## 5. Backups & Disaster Recovery Runbook

### 5.1 Automated Backup Creation

Run the backup manager:
```bash
python scripts/backup_manager.py create --tag manual_scheduled
```
- **Backup Location:** `data/backups/backup_<timestamp>_<tag>/`
- **What is Backed Up:**
  1. `data/raw/eureka_website_data.json`
  2. `data/processed/eureka_website_chunks.json`
  3. `data/vectorstore/chroma.sqlite3` (checkpointed from WAL)
  4. `data/vectorstore/index_manifest.json`
  5. `data/vectorstore/<collection-uuid>/` binary HNSW trees
  6. `data/reports/` (all crawl and indexing reports)
  7. Cryptographic `backup_manifest.json` with SHA-256 digests of all 16 files.
- **Estimated Size:** ~31 MB per snapshot.

### 5.2 Backup Retention Policy
- Retain daily backups for 7 days.
- Retain weekly backups for 4 weeks.
- Retain monthly release backups indefinitely.
- Automated cleanup command:
  ```bash
  # Delete backups older than 30 days
  find data/backups/ -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
  ```

---

### 5.3 Automated Isolated Restore Test

Always test restore procedures in an isolated directory without touching the active production database:

```bash
python scripts/backup_manager.py restore-test
```
- **What this does:**
  1. Verifies SHA-256 checksums of all 16 files against `backup_manifest.json`.
  2. Unpacks files into `data/restore_test_isolated/`.
  3. Mounts the isolated ChromaDB database.
  4. Verifies collection exists with exactly 3,796 records.
  5. Runs live semantic search queries (`"What ERP software does Eureka Solutions implement?"`).
  6. Measures retrieval latency and distances.
  7. Releases file locks and unmounts clean sandbox.
- **Expected Outcome:** `RESTORE TEST RESULT: PASS in ~22 seconds.`

---

## 6. Incident Response Runbooks

### Incident 1: Frontend Cannot Reach Backend (Network / 502 Bad Gateway)
1. **Check Nginx Reverse Proxy:**
   ```bash
   sudo systemctl status nginx
   sudo tail -n 20 /var/log/nginx/error.log
   ```
2. **Check Backend Process:**
   ```bash
   curl -v http://127.0.0.1:8000/health/live
   ```
   - If connection refused: backend is down. Start it: `sudo systemctl start eureka-backend`.
   - If port conflict: identify occupying process: `sudo lsof -i :8000`.

---

### Incident 2: CORS Rejection ("No 'Access-Control-Allow-Origin' header")
1. Check client browser Origin in developer console (e.g. `https://eurekasolutions.in`).
2. Inspect `ALLOWED_ORIGINS` in `.env`:
   ```bash
   grep "ALLOWED_ORIGINS" .env
   ```
3. Ensure the exact origin is listed with matching scheme and port, without trailing slash.
4. Restart backend: `sudo systemctl restart eureka-backend`.

---

### Incident 3: Readiness Probe Fails (HTTP 503 "not_ready")
1. Inspect ready response:
   ```bash
   curl http://127.0.0.1:8000/health/ready
   ```
2. **Case A: `status: "not_ready", reason: "vector_store_empty"`**
   - The ChromaDB database has 0 records.
   - Run restore: `python scripts/backup_manager.py restore-test` or rebuild: `python -m scripts.build_index`.
3. **Case B: `status: "not_ready", reason: "index_incompatible"`**
   - Embedding model name in `.env` differs from `index_manifest.json`.
   - Ensure `EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2` in `.env`.

---

### Incident 4: Vector Index Corrupted or Missing
1. Stop backend service:
   ```bash
   sudo systemctl stop eureka-backend
   ```
2. Restore from latest verified backup:
   ```bash
   # Identify latest backup
   python scripts/backup_manager.py list
   # Copy verified backup directory to data/vectorstore
   cp -r data/backups/backup_<timestamp>/vectorstore/* data/vectorstore/
   ```
3. Start backend service:
   ```bash
   sudo systemctl start eureka-backend
   ```
4. Verify `/health/ready` returns HTTP 200 with 3,796 records.

---

### Incident 5: OpenAI Upstream Failure (Timeouts / Outages)
- The application automatically handles OpenAI outages cleanly:
  - Timeouts (exceeding 30.0s) and transient 5xx errors undergo 2 bounded retries with backoff.
  - If still failing, the API returns HTTP 503 with standardized `ErrorResponse` and friendly user notice:
    *"Our assistant is temporarily unavailable while communicating with our language model. Please try again shortly."*
  - Zero raw tracebacks, internal prompts, or API keys are ever leaked to the user.
- **Action:** Check [OpenAI Status Page](https://status.openai.com/). If prolonged outage, switch `LLM_PROVIDER=groq` in `.env` as fallback and restart.

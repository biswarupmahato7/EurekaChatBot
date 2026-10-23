# Eureka RAG Chatbot — Phase A Website Data Pipeline

## 1. Overview

This directory (`crawler/`) contains the complete **Phase A Website Data Pipeline** for the **Eureka RAG Chatbot**.

The pipeline is responsible for:
- Discovery of approved public content from the Eureka Solutions website
- Safe, rate-limited HTTP fetching with SSRF and size protections
- HTML parsing, boilerplate stripping, and semantic content extraction
- Schema 1.0 structured JSON export (`data/raw/eureka_website_data.json`)
- Token-aware, structure-aware semantic chunking (`data/processed/eureka_website_chunks.json`)
- Checkpoints and failure-safe incremental crawling
- Validation reports and ZIP packaging for downstream Phase B retrieval

---

## 2. Target Website & Discovery Findings (A.0)

| Attribute | Verified Finding |
|---|---|
| **Target URL** | `https://eurekasolutions.in/Eureka2026/` |
| **Approved Origin** | `eurekasolutions.in` |
| **Approved Path Prefix** | `/Eureka2026/` |
| **Sitemap URL** | `https://eurekasolutions.in/Eureka2026/sitemap.xml` (103 URLs) |
| **Rendering Behavior** | Server-rendered HTML (full text present in static HTML; no Playwright required) |
| **Robots Policy** | `robots.txt` returns 404 (no crawler restrictions) |
| **Path Structure** | Sitemap links omit `/Eureka2026/`; crawler automatically normalises and adds the prefix |

---

## 3. Architecture & Components

```text
crawler/
├── cli/
│   ├── crawl_website.py     # CLI: Bounded/full web crawler
│   ├── create_chunks.py     # CLI: Token-aware chunk generation
│   ├── package_data.py      # CLI: Pack and verify eureka-rag-data.zip
│   ├── run_pipeline.py      # CLI: End-to-end pipeline orchestrator
│   └── validate_data.py     # CLI: Schema and dataset integrity validator
├── tests/
│   ├── fixtures/            # Local HTML and XML fixtures for 100% offline tests
│   ├── test_checkpoints.py  # Checkpoint save/load/cleanup tests
│   ├── test_chunker.py      # Token limits, overlap, section splitting tests
│   ├── test_cli_packaging.py# CLI commands and ZIP deliverable verification tests
│   ├── test_config_models.py# Pydantic schemas and settings tests
│   ├── test_discovery.py    # URL queue, sitemap, depth/page bound tests
│   ├── test_fetcher.py      # SafeFetcher, retries, SSRF, robots cache tests
│   ├── test_hashing.py      # Deterministic SHA-256 ID stability tests
│   ├── test_parser.py       # HTML parsing, boilerplate removal, Unicode tests
│   ├── test_pipeline_incremental.py # Incremental crawl and failure-safe tests
│   ├── test_smoke.py        # Python 3.11 environment smoke test
│   ├── test_url_utils.py    # URL normalisation, scope, SSRF, trap tests
│   └── test_validation.py   # Raw & chunk validator tests
├── checkpoints.py           # Atomic checkpoint persistence
├── chunker.py               # Structure- and token-aware chunking
├── config.py                # Pydantic BaseSettings with environment overrides
├── discovery.py             # URL discovery queue and sitemap parser
├── fetcher.py               # SafeFetcher with retry and SSRF guards
├── hashing.py               # SHA-256 stable hashing
├── logging_config.py        # Structured logging configuration
├── models.py                # Schema 1.0 Pydantic models
├── packaging.py             # Archive creation and verification
├── parser.py                # BeautifulSoup HTML parser and content cleaner
├── pipeline.py              # Full & incremental crawl orchestration
├── reports.py               # Crawl & chunking report generation
├── requirements.txt         # Pinned crawler dependencies
├── url_utils.py             # URL normalisation and SSRF security
└── README.md                # This file
```

---

## 4. CLI Entry Points

All commands work across Windows PowerShell and Unix-like shells.

### Run Full End-to-End Pipeline (Crawl -> Chunk -> Validate)
```powershell
.\.venv\Scripts\python.exe -m crawler.cli.run_pipeline --mode full --max-pages 110 --delay 1.0
```

### Run Incremental Pipeline (Only fetches changed content, preserves existing data on failure)
```powershell
.\.venv\Scripts\python.exe -m crawler.cli.run_pipeline --mode incremental
```

### Crawl Only
```powershell
# Dry run: discover URLs and sitemap without making page GET requests
.\.venv\Scripts\python.exe -m crawler.cli.crawl_website --dry-run

# Conservative live crawl
.\.venv\Scripts\python.exe -m crawler.cli.crawl_website --max-pages 50 --delay 1.5
```

### Generate Chunks
```powershell
.\.venv\Scripts\python.exe -m crawler.cli.create_chunks --target-tokens 500 --overlap 75 --max-tokens 700
```

### Validate Datasets
```powershell
.\.venv\Scripts\python.exe -m crawler.cli.validate_data --dataset both
```

### Package Deliverable
```powershell
.\.venv\Scripts\python.exe -m crawler.cli.package_data
```

---

## 5. Incremental Crawling & Failure-Safe Preservation

1. **Deterministic Hashing**: Every page has a stable SHA-256 `page_id` based on its canonical/source URL, and a `content_hash` based on cleaned text and title.
2. **Unchanged Content**: During incremental runs, if the extracted content hash matches the previous run, the page is preserved without regenerating chunks.
3. **Failure Isolation**: A transient HTTP 429, 500, or network timeout on a previously crawled page will **never** drop that page from the dataset. The previous valid record is automatically preserved.
4. **Atomic Writes**: All raw datasets, chunk datasets, and checkpoints are written to temporary files and atomically renamed (`os.replace`) to eliminate corruption risks.

---

## 6. Testing Strategy

All unit and integration tests run **100% offline** against local HTML/XML fixtures in `crawler/tests/fixtures/`. No live network calls or API keys are required.

To run the full test suite:
```powershell
.\.venv\Scripts\python.exe -m pytest
```

---

## 7. Mandatory Phase Boundary

- **No Groq calls, LLM calls, or embedding generation** occur in this phase.
- **No vector index (ChromaDB, pgvector, etc.)** is initialized.
- **No secrets, virtual environments, or caches** are packaged into deliverables.

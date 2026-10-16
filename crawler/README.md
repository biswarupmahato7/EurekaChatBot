# Crawler — `crawler/`

## Responsibility

This directory contains the **Phase A website data pipeline** for the Eureka RAG Chatbot.

The crawler discovers, fetches, extracts, cleans, and chunks approved public content from the Eureka Solutions website (`https://eurekasolutions.in/Eureka2026/`) and produces structured JSON datasets for the retrieval pipeline.

## Current status

**Phase 0 — Repository bootstrap only.** The crawler implementation begins in Phase A.

The directory structure and dependency declarations are in place. No source code, live crawl output, or production data exists yet.

## Intended structure (Phase A onwards)

```text
crawler/
├── src/                    # Source modules
│   ├── __init__.py
│   ├── config.py           # Validated Pydantic settings
│   ├── models.py           # Pydantic schemas for raw/chunked records
│   ├── url_utils.py        # URL normalization, scope enforcement, SSRF guards
│   ├── discovery.py        # Queue, sitemap, internal-link discovery
│   ├── fetcher.py          # robots.txt, HTTP fetch, retries, redirects
│   ├── parser.py           # HTML field extraction
│   ├── cleaner.py          # Boilerplate removal
│   ├── chunker.py          # Token-aware, structure-aware chunking
│   ├── hashing.py          # SHA-256 content hashes, deterministic IDs
│   ├── export.py           # Atomic JSON write
│   ├── validator.py        # Schema and data quality checks
│   └── pipeline.py         # Orchestration, checkpoints, reports
├── scripts/                # CLI entry points (Phase A)
│   ├── crawl_website.py
│   ├── create_chunks.py
│   ├── run_pipeline.py
│   └── validate_data.py
├── tests/
│   ├── __init__.py
│   ├── test_smoke.py       # Phase 0 smoke test (runs now)
│   └── fixtures/           # HTML fixtures for unit tests (Phase A)
├── __init__.py
├── requirements.txt
└── README.md
```

## Dependencies

Install crawler dependencies (no API keys required):

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r crawler/requirements.txt
```

```bash
# Linux / macOS
python -m venv .venv
source .venv/bin/activate
pip install -r crawler/requirements.txt
```

## Running the smoke test (Phase 0)

```powershell
python -m pytest crawler/tests -v
```

## Key design decisions

- **Python 3.11+** required.
- **No Groq/embedding API key** is ever needed to run or test the crawler.
- **tiktoken** (`cl100k_base` encoding by default) is the initial tokenizer. The same encoding must be used consistently for chunking and validation. See `crawler/requirements.txt` for the tokenizer note.
- All HTTP requests use a descriptive `User-Agent` and respect `robots.txt`.
- Crawl boundaries are enforced: only `https://eurekasolutions.in/Eureka2026/` and explicitly allow-listed paths.
- Outputs are written atomically (write to temp → validate → replace) to prevent data corruption.
- Never commit real crawled data or secrets to Git.

## What belongs here

- Crawler source modules under `src/`.
- CLI scripts under `scripts/`.
- Unit and integration tests under `tests/` using **local HTML fixtures only** — no live network calls in tests.
- Crawler-specific dependency declarations in `requirements.txt`.

## What does NOT belong here

- FastAPI endpoints, Groq integration, or vector database code — those are in `backend/`.
- Frontend widget code — that is in `frontend/` (Phase D) or `frontend-integration/`.
- Real crawled JSON datasets — those are generated into `data/raw/` and `data/processed/` and are not tracked by Git.

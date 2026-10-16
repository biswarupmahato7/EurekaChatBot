# Tests — `tests/`

## Responsibility

This directory contains **top-level integration and cross-component tests** that span more than one package (crawler + backend, or backend + data), implemented in later phases.

Per-component unit tests live alongside their source code:

| Component | Test location |
|-----------|---------------|
| Crawler | `crawler/tests/` |
| Backend/API | `backend/tests/` |
| Cross-component / integration | `tests/` ← **this directory** |

## Current status

**Phase 0 — Directory stub only.** No integration tests exist yet.

The first runnable tests are in `crawler/tests/test_smoke.py` and can be executed immediately:

```powershell
python -m pytest crawler/tests -v
```

## What belongs here (future phases)

- End-to-end tests that exercise the full pipeline: crawler output → index build → API retrieval → response.
- Data integrity checks that validate consistency across `data/raw/` and `data/processed/`.
- Shared test fixtures and helpers reused by multiple test packages.
- Answer-quality evaluation suites (Phase E).

## What does NOT belong here

- Crawler-specific unit tests (those go in `crawler/tests/`).
- Backend-specific unit tests (those go in `backend/tests/`).
- Live website crawl tests (Phase A final acceptance only, clearly labeled).
- Tests that require real Groq API credentials (mock them; use real provider only in controlled staging smoke).

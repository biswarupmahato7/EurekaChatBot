# Frontend Integration — `frontend-integration/`

## Responsibility

This directory documents the **integration contract** between the Eureka RAG Chatbot backend API and the existing Eureka Solutions website frontend.

The frontend team may implement their own `frontend/` application or widget during **Phase D**. This directory focuses on the API contract, integration requirements, and handoff materials — not on frontend implementation code.

## Current status

**Phase 0 — Directory stub only.** Integration documentation will be populated in Phase C (API contract delivery) and Phase D (widget integration).

## Intended contents (Phase C/D onwards)

```text
frontend-integration/
├── README.md                   # ← this file
├── API_CONTRACT.md             # Full API contract with payloads and errors
│                               #   (also in docs/ — cross-linked here)
├── sample-requests/
│   ├── chat_request.json       # Sample POST /api/v1/chat request body
│   ├── chat_response_ok.json   # Sample successful response
│   └── chat_response_fallback.json  # Sample insufficient-evidence response
├── cors-config-notes.md        # Allowed origins per environment
└── widget-integration-guide.md # How to embed the Ask Eureka AI widget
```

## API contract summary (target — Phase C)

The backend will expose the following endpoints (see `docs/architecture.md` §6.2 for details):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health/live` | GET | Liveness check |
| `/health/ready` | GET | Readiness check |
| `/api/v1/chat` | POST | Question answering with citations |
| `/api/v1/feedback` | POST | Optional thumbs-up/down feedback |

## Frontend integration requirements

- Read the API base URL from deployment configuration — **never hard-code it**.
- Send `POST /api/v1/chat` with JSON body `{ "message": "...", "session_id": "...", "language": "auto" }`.
- Handle all response statuses: `answered`, `insufficient_evidence`, `out_of_scope`, `temporarily_unavailable`.
- **Never** call Groq directly from the browser.
- **Never** include the `GROQ_API_KEY` or vector database credentials in client-side code.
- CORS is configured for specific allowed origins — coordinate with the backend team before changing origins.
- Display source links from the `sources` array; open in a new tab with `rel="noopener noreferrer"`.
- Sanitize/escape all model output — never render raw HTML from the API response.

## Handoff responsibilities

| Team | Must deliver |
|------|-------------|
| **Backend team** | API base URL per environment, OpenAPI schema export, sample request/response payloads, error-state definitions, allowed CORS origins, test endpoint |
| **Frontend team** | Widget source, list of required environment variables, setup instructions, staging integration-test record |

## What belongs here

- API contract documentation and sample payloads.
- CORS configuration notes.
- Widget integration guides.
- Frontend environment variable documentation.

## What does NOT belong here

- Frontend application source code (that belongs in `frontend/`, owned by the frontend team in Phase D).
- Backend implementation code (that belongs in `backend/`).
- Crawler source code (that belongs in `crawler/`).

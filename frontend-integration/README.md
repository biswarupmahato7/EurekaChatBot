# Frontend Integration — `frontend-integration/`

## 1. Responsibility

This directory documents the **integration contract**, handoff materials, sample request/response payloads, and embedding guide for the **Ask Eureka AI** widget (`frontend/`).

## 2. Directory Structure

```text
frontend-integration/
├── README.md                          # ← This overview
├── widget-integration-guide.md        # Step-by-step embedding instructions
├── cors-config-notes.md               # Origin allow-list rules per environment
└── sample-requests/
    ├── chat_request.json              # Canonical POST /api/v1/chat request
    ├── chat_response_ok.json          # Standard grounded response with citations
    ├── chat_response_fallback.json    # Insufficient evidence response
    └── chat_response_outofscope.json  # Out-of-scope response
```

## 3. Quick Reference

- **Target Backend Endpoint:** `POST /api/v1/chat`
- **Request Schema:**
  ```json
  {
    "message": "What ERP services does Eureka Solutions provide?",
    "session_id": "client-sess-1234",
    "language": "auto"
  }
  ```
- **Response Schema:**
  ```json
  {
    "request_id": "req-3fa85f64e042",
    "answer": "Eureka Solutions provides...",
    "status": "answered",
    "sources": [
      {
        "title": "Oracle NetSuite ERP Services",
        "url": "https://eurekasolutions.in/Eureka2026/services/netsuite/",
        "snippet": "..."
      }
    ],
    "message": null
  }
  ```

- **Frontend Widget Location:** `d:/Eureka Chat bot/frontend/`
- **Full Integration Guide:** See [`docs/FRONTEND_INTEGRATION.md`](../docs/FRONTEND_INTEGRATION.md)
- **Staging Test Record:** See [`docs/STAGING_TEST_RECORD.md`](../docs/STAGING_TEST_RECORD.md)

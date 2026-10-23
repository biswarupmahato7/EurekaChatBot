# Eureka RAG Chatbot — API Contract & Integration Guide

**Version:** 1.0.0  
**Target Environment:** Local Development & Staging  
**FastAPI Service Base Path:** `/api/v1`  
**Interactive OpenAPI Documentation:** Available at `http://127.0.0.1:8000/docs` (disabled in production via `APP_ENV=production` or `ENABLE_DOCS=false`).

---

## 1. Overview & Architectural Role

The Eureka RAG Chatbot Backend is a FastAPI service that performs grounded Question-Answering over the crawled Eureka Solutions website corpus (`https://eurekasolutions.in/Eureka2026/`).

### Expected Request Flow
```
Frontend Web Client
      │
      ▼  (POST /api/v1/chat)
FastAPI Middleware (Request-ID, Exact CORS, Sliding-Window IP Rate Limiter)
      │
      ▼
Request Schema Validation (Trimmed message, 1 <= length <= 2000, optional conversation_history)
      │
      ▼
Smart Conversation Router (Deterministic categorization & boundary checks)
  ├── OFF_TOPIC (Trivia, Food, Sports, Weather) ───────────────► Return 200 (status: "out_of_scope", zero OpenAI/vector cost)
  ├── ABUSIVE_OR_INSULTING (Bot insults, Standalone vulgarity) ──► Return 200 (status: "out_of_scope", calm redirect / firm boundary)
  └── WEBSITE_QUERY / WEBSITE_QUERY_WITH_PROFANITY / FOLLOW_UP
            │
            ▼
      Contextual Reference Resolution (Recent turn continuity, query sanitization)
            │
            ▼
      Semantic Retrieval (Top-k dense cosine search on ChromaDB)
            │
            ▼
      Evidence Sufficiency Evaluation (Relevance threshold >= 0.20, candidate text length check)
        ├── INSUFFICIENT ────────────────────────────────────► Return 200 (status: "insufficient_evidence")
        └── SUFFICIENT
                  │
                  ▼
            Controlled Prompt Builder (Evidence-only system prompt, professional profanity handling)
                  │
                  ▼
            Isolated OpenAI Client (Responses API, Model: gpt-4o-mini, 30s timeout, bounded retries)
                  │
                  ▼
            Citation Builder & Output Sanitizer (Metadata-grounded citations, strip external URLs)
                  │
                  ▼
            Grounded Response (Return 200, status: "answered")
```

---

## 2. Global Request & Response Rules

1. **Request Correlation (`X-Request-ID`):**
   - Every response contains an `X-Request-ID` HTTP header formatted as `req-<hex>` (e.g. `req-4c3d2e1a0f9b`).
   - Every JSON payload (success or error) contains `request_id`.
   - The frontend should log or present this ID to users in error states for troubleshooting.
2. **CORS:**
   - Allowed origins are strictly enforced based on server configuration.
   - Development defaults: `http://localhost:3000`, `http://127.0.0.1:3000`, `https://eurekasolutions.in`.
   - Disallowed origins will be rejected by preflight (`OPTIONS`) without `Access-Control-Allow-Origin`.
3. **Rate Limiting:**
   - Per-client-IP sliding-window limiter (default: 60 requests per minute).
   - If exceeded, returns HTTP `429 Too Many Requests` with a `Retry-After: 60` header.

---

## 3. Endpoints Specification

### 3.1 Process Liveness Probe

`GET /health/live`

Verifies that the FastAPI process is running. Fast, performs zero external network calls or vector searches.

**Response:** `HTTP 200 OK`
```json
{
  "status": "ok"
}
```

---

### 3.2 Dependency Readiness Probe

`GET /health/ready`

Verifies that the backend is ready to serve queries. Checks ChromaDB connectivity and confirms the knowledge collection (`eureka_website_chunks`) exists with indexed chunks. Never calls OpenAI or external LLMs.

**Success Response:** `HTTP 200 OK`
```json
{
  "status": "ready",
  "vector_store": "ok",
  "collection": "eureka_website_chunks",
  "chunks_count": 3796
}
```

**Unready Response:** `HTTP 503 Service Unavailable`
```json
{
  "status": "not_ready",
  "reason": "collection_empty_or_missing",
  "collection": "eureka_website_chunks",
  "detail": "Vector index collection is empty or not found."
}
```

---

### 3.3 Chat Question-Answering

`POST /api/v1/chat`

Submit visitor inquiries and receive grounded answers with citations.

#### Request Headers
| Header | Type | Required | Description |
|---|---|---|---|
| `Content-Type` | string | Yes | Must be `application/json` |
| `X-Request-ID` | string | No | Optional client-supplied tracing ID (max 128 chars) |

#### Request Body (`ChatRequest`)
| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `message` | string | **Yes** | 1 to 2,000 characters | The visitor's question text. Cannot be empty or whitespace-only. |
| `session_id` | string | No | Max 128 chars, no control characters | Opaque client-side identifier. |
| `language` | string | No | Default: `"auto"` | Target language code or `"auto"` to preserve inquiry language. |
| `conversation_history` | list[`ConversationTurn`] | No | Max 6 turns | Bounded, privacy-conscious list of recent user and assistant turns for contextual reference resolution. |

#### Conversation Turn (`ConversationTurn`)
| Field | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `role` | string | **Yes** | `"user"` or `"assistant"` | Origin of the conversation turn. |
| `content` | string | **Yes** | 1 to 1,000 characters | Cleaned message text from the recent interaction. |

**Example Request:**
```json
{
  "message": "Do they have an office in Goa?",
  "session_id": "client-sess-9872",
  "language": "auto",
  "conversation_history": [
    {
      "role": "user",
      "content": "Where is Eureka Solutions based?"
    },
    {
      "role": "assistant",
      "content": "Eureka Solutions is based in Mumbai, India."
    }
  ]
}
```

---

#### Response Body (`ChatResponse`)
| Field | Type | Description |
|---|---|---|
| `request_id` | string | Server-generated correlation ID matching `X-Request-ID`. |
| `answer` | string | Grounded markdown answer or polite fallback message. |
| `status` | string | Logical resolution status (`answered`, `insufficient_evidence`, `out_of_scope`, `temporarily_unavailable`). |
| `sources` | list[`SourceItem`] | Verified citations extracted from retrieved website chunks. (Preserved for backend validation; hidden in client UI). |
| `quick_replies` | list[string] | Contextual quick-reply chips for intent clarification or guided next steps (e.g. `["Discuss a project", "Ask about services", ...]`). |
| `message` | string or null | Optional operational or contextual notice. |

#### Source Item (`SourceItem`)
| Field | Type | Description |
|---|---|---|
| `title` | string | Title of the source webpage or section heading. |
| `url` | string | Validated URL under `https://eurekasolutions.in/`. |
| `snippet` | string | Grounded text excerpt from the retrieved website chunk. |

---

## 4. Logical Statuses & HTTP Code Mappings

The backend cleanly separates **HTTP transport codes** from **conversational outcomes**:

| Status | HTTP Code | Meaning | Sources Returned | Internal Outcome Category |
|---|---|---|---|---|
| `answered` | `200 OK` | The system retrieved sufficient evidence from the website, Groq generated the answer, and all citations are verified. | 1 or more verified citations. | `ANSWERABLE_IN_SCOPE` |
| `insufficient_evidence` | `200 OK` | The inquiry is company-related, but the crawled website does not verify the requested fact (e.g. Goa office, unverified pricing/guarantee). Provides honest distinction of known vs unknown facts. | Citations for known context (or empty). | `IN_SCOPE_INSUFFICIENT` |
| `out_of_scope` | `200 OK` | The inquiry is unrelated to Eureka Solutions' business scope (e.g., food, cricket/sports, general trivia, insults). Returns a brief, friendly redirect without hallucinated facts. | Empty `[]`. | `UNRELATED_OUT_OF_SCOPE` |
| `temporarily_unavailable` | `503 Service Unavailable` | Downstream retrieval or Groq LLM service timed out or is temporarily unavailable. | Empty `[]`. | `TEMPORARILY_UNAVAILABLE` |

### 4.1 Smart Conversation Router Categories (Internal)

| Router Category | Criteria | RAG Action | Response Policy |
|---|---|---|---|
| `website_query` | Company questions, services, solutions, case studies, industries. | Full RAG pipeline | Grounded answers strictly backed by retrieved evidence chunks. |
| `off_topic` | General trivia, culinary recipes, live weather, sports results. | Bypasses RAG & Groq | Short, friendly redirect mentioning verified software services. |
| `abusive_or_insulting` | Standalone bot insults ("You are useless") or standalone profanity. | Bypasses RAG & Groq | Calm, polite redirect. Escalates to a firm boundary only upon repeated turns without retaliation. |
| `website_query_with_profanity` | User query contains profanity but also asks a genuine website question. | Sanitized RAG pipeline | Strips vulgarity for vector embedding. Answers the valid inquiry professionally without scolding or echoing vulgarity. |
| `mixed_or_ambiguous` | User feedback/criticism ("Your previous answer was wrong") or ambiguous query. | Full RAG pipeline | Does NOT classify feedback as abuse. Solicits clarification or re-evaluates inquiry. |
| `follow_up` | Contextual queries referring back to company services after any prior turn. | Contextual RAG pipeline | Resolves pronouns (`they`, `their`, `it`) using recent history and immediately restores normal RAG retrieval. |



---

## 5. Standardized Public Error Response

When input validation fails, rate limits are hit, or server exceptions occur, the API returns a structured `ErrorResponse`:

```json
{
  "request_id": "req-7f8e9d0a1b2c",
  "error": {
    "code": "validation_error",
    "message": "Invalid request payload or schema constraints not met.",
    "request_id": "req-7f8e9d0a1b2c",
    "details": [
      {
        "field": "body -> message",
        "issue": "Message exceeds maximum allowed limit of 2,000 characters."
      }
    ]
  }
}
```

### Common Error Codes:
- `validation_error` (`HTTP 422`): Missing required fields, empty text, or message > 2,000 characters.
- `rate_limit_exceeded` (`HTTP 429`): Exceeded 60 requests/minute. Check `Retry-After` header.
- `internal_error` (`HTTP 500`): Unexpected server error (sanitized, stack traces are never exposed).

---

## 6. Sample Request & Response Scenarios

### Scenario A: Grounded Answer (`status: "answered"`)
**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What ERP software do you implement?"}'
```
**Response (`HTTP 200 OK`):**
```json
{
  "request_id": "req-3fa85f64e042",
  "answer": "Eureka Solutions specializes in Oracle NetSuite ERP implementations, Cloud Data Integration, and bespoke software solutions.",
  "status": "answered",
  "sources": [
    {
      "title": "Oracle NetSuite ERP Services",
      "url": "https://eurekasolutions.in/Eureka2026/services/netsuite/",
      "snippet": "Eureka Solutions is an award-winning Oracle NetSuite implementation and customization partner."
    }
  ],
  "message": null
}
```

### Scenario B: Insufficient Evidence (`status: "insufficient_evidence"`)
**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What was Eureka Solutions stock price in 1995?"}'
```
**Response (`HTTP 200 OK`):**
```json
{
  "request_id": "req-9b8c7d6e5f4a",
  "answer": "I couldn't find enough information about that in the available Eureka Solutions website content. Please check the official website at https://eurekasolutions.in/Eureka2026/ for more details.",
  "status": "insufficient_evidence",
  "sources": [],
  "message": null
}
```

### Scenario C: Out of Scope (`status: "out_of_scope"`)
**Request:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in London right now?"}'
```
**Response (`HTTP 200 OK`):**
```json
{
  "request_id": "req-1a2b3c4d5e6f",
  "answer": "I am the Ask Eureka AI assistant, designed specifically to help with information about Eureka Solutions, our enterprise services, technology solutions, industries, and client case studies. I cannot assist with queries outside this scope. Please feel free to ask about our software engineering, AI automation, or industry solutions.",
  "status": "out_of_scope",
  "sources": [],
  "message": null
}
```

---

## 7. Developer Quickstart & Configuration

### Prerequisites
- Python 3.11+
- Virtualenv with requirements installed (`pip install -r requirements.txt`)
- Populated Phase B vector store at `./data/vectorstore` (collection: `eureka_website_chunks`)

### Environment Variables (`.env`)
```bash
# Application Environment
APP_ENV=development
APP_HOST=127.0.0.1
APP_PORT=8000

# CORS Allowed Origins (Comma-separated)
ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://eurekasolutions.in

# Groq LLM Credentials (Backend Only)
GROQ_API_KEY=gsk_your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_TIMEOUT_SECONDS=30
GROQ_MAX_RETRIES=2
GROQ_MAX_OUTPUT_TOKENS=1024

# Vector Store (Phase B Index)
CHROMA_PERSIST_DIRECTORY=./data/vectorstore
CHROMA_COLLECTION=eureka_website_chunks

# Rate Limiting & Proxy Configuration
RATE_LIMIT_PER_MINUTE=60
TRUSTED_PROXIES=127.0.0.1
```

### Running Local Development Server
```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Exporting OpenAPI Specification
```powershell
.\.venv\Scripts\python.exe scripts/export_openapi.py docs/openapi.json
```

---

## 8. Phase C Exclusions & Scope Boundaries

- **No Server-Side Session Persistence:** The backend does not persist conversation state or historical user turns in Phase C. Each query is evaluated independently.
- **No Direct Frontend Database Access:** Frontend clients must only interact via HTTP with `/api/v1/chat`. Direct ChromaDB access from client-side is strictly prohibited.
- **No Personal Data Harvesting:** The API does not accept or store user names, email addresses, or phone numbers.

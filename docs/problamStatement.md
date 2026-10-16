# Problem Statement: Eureka Solutions Website RAG Chatbot — Complete End-to-End Specification

**Project:** Eureka Solutions — Ask Eureka AI  
**Website:** https://eurekasolutions.in/Eureka2026/  
**Document type:** Product, technical, implementation, integration, and acceptance specification  
**Version:** 2.0  
**Status:** Implementation-ready baseline; confirm any website-specific design decisions with the relevant team  
**Primary goal:** Build a website chatbot that answers visitors' questions using traceable information from the approved Eureka Solutions website content.

---

## 1. Executive Summary

Eureka Solutions needs an **Ask Eureka AI** chatbot that visitors can open from the existing website. The chatbot should answer questions about the company, services, solutions, projects, industries, published contact information, and other topics that are actually documented in the approved website content. It must retrieve relevant source content before generating an answer and show visitors the pages used to support that answer.

The project includes the complete flow:

1. Discover and crawl approved public website pages.
2. Extract, clean, validate, and chunk website content.
3. Generate embeddings and index the chunks in a vector store.
4. Receive user questions through a secured backend API.
5. Retrieve relevant content, apply scope and grounding checks, and call the configured LLM through Groq's API.
6. Return a well-formatted answer with source links to the website frontend.
7. Integrate a responsive chat widget into the existing website.
8. Test, deploy, monitor, and document the complete solution.

The frontend and backend can be owned by separate teams, but they must agree on the API contract and coordinate integration testing. The implementation must not invent website facts or claim the live crawl has succeeded until the site has actually been crawled and the output validated.

## 2. Background and Problem Statement

Important company information is distributed across multiple pages. Raw HTML includes scripts, styling, repeated navigation, footer content, links, and layout markup that are not suitable as direct retrieval context. A general-purpose LLM alone may produce unsupported answers, guess about company offerings, or answer unrelated questions without grounding.

A reliable website RAG chatbot is therefore required. The system must transform approved website content into a searchable knowledge base and use retrieved source passages to answer visitor questions. If the relevant information is not found, the chatbot should clearly say that it could not find a supported answer and direct the user to the official website or contact route when available, instead of fabricating details.

## 3. Objectives

- Provide a simple **Ask Eureka AI** entry point on the existing website.
- Answer questions using approved, publicly accessible website content.
- Preserve source URLs and page/section metadata throughout crawling, chunking, retrieval, and response generation.
- Produce readable answers with short paragraphs, headings or bullets where useful, and clickable source references.
- Detect unrelated or unsupported questions and respond safely.
- Keep LLM and database credentials on the backend; never expose them in browser code.
- Support a practical initial workload of approximately 50 visitor sessions per day, subject to actual message volume and provider quotas.
- Keep the pipeline reproducible so the knowledge base can be refreshed when the website changes.
- Provide code, tests, documentation, deployment instructions, and verifiable acceptance evidence.

## 4. Users, Ownership, and Workstreams

### 4.1 End users

Website visitors who want to learn about Eureka Solutions using information published on the website.

### 4.2 Frontend team

Responsible for the chat widget, responsive user experience, API integration, displaying answers and sources, UI error states, and coordinating final integration with the existing site.

### 4.3 Backend/RAG team

Responsible for the crawler and processing pipeline, vector index, retrieval and generation pipeline, API contracts, Groq integration, grounding and scope controls, backend security, logging, tests, deployment, and technical handoff.

### 4.4 Project owner/reviewer

Approves website crawl scope, checks answer quality, confirms source links and branding, reviews deployment access, and signs off against the acceptance criteria.

### 4.5 Suggested implementation phases

- **Phase A — Website data pipeline:** crawl, extract, clean, chunk, validate, create report and data ZIP.
- **Phase B — Retrieval foundation:** embedding model, vector database, index build/update, and retrieval tests.
- **Phase C — Backend chatbot:** scope checks, prompt construction, Groq LLM client, citations, FastAPI endpoints, security, logs.
- **Phase D — Frontend:** Ask Eureka AI widget and agreed API integration.
- **Phase E — Integration and evaluation:** end-to-end tests, answer quality, failure handling, accessibility, and responsiveness.
- **Phase F — Deployment and handoff:** hosting, environment configuration, backups, monitoring, and runbooks.

---

## 5. Scope

### 5.1 In scope

- Crawling approved, publicly accessible pages under the configured Eureka website scope.
- Optional discovery through XML sitemap and internal links.
- URL normalization, duplicate prevention, rate limiting, bounded retries, and detailed crawl reporting.
- Extracting titles, descriptions, headings, main text, useful lists/tables, relevant alt text, canonical/final URLs, and internal links.
- Creating versioned raw JSON and chunked JSON datasets.
- Token-aware, structure-aware chunking and content hashes.
- Embedding generation using a configurable model.
- Vector database ingestion, search, metadata filtering, and index refreshes.
- FastAPI backend and documented HTTP API.
- Groq chat-completion integration using a backend-only API key and configurable model ID.
- Scope classification, retrieval thresholds, prompt grounding, source validation, answer formatting, and graceful fallback responses.
- Frontend widget integration with the existing website.
- Operational security, automated testing, logs, deployment docs, and handoff package.

### 5.2 Out of scope unless separately approved

- Accessing private pages, authenticated portals, or content blocked by site permissions.
- Bypassing CAPTCHA, robots rules, rate limits, or other access controls.
- Crawling unrelated domains as a general web search engine.
- Training or fine-tuning a foundation model.
- Giving professional legal, financial, medical, or other high-stakes advice.
- Guaranteeing that every possible visitor question can be answered.
- Collecting sensitive personal information that is not needed for chat functionality.
- Building a customer login system or retaining conversation history indefinitely.
- Making changes to the core website beyond the agreed widget integration.
- Adding paid APIs or hosted infrastructure without approval.

---

## 6. Target Website and Crawl Boundaries

**Starting URL:** `https://eurekasolutions.in/Eureka2026/`

By default, crawl only the approved origin and the `/Eureka2026/` path prefix. Additional paths or domains must be explicitly allow-listed after review. The following are possible content categories to discover, not claims that these pages currently exist: company profile, services, solutions, technologies, industries, case studies, portfolio/projects, FAQs, published contact information, and other relevant linked pages.

### 6.1 Crawling rules

- Check and respect `robots.txt`, the website's applicable terms, and reasonable request frequency.
- Use a descriptive User-Agent with a project contact where appropriate.
- Configure page limit, crawl depth, timeout, response size, retries, request delay, and concurrency.
- Discover URLs from approved internal links and a sitemap, if one is available.
- Normalize trailing slashes, fragments, default ports, host casing, and known tracking parameters consistently.
- Reject external links by default; skip mailto, tel, JavaScript links, irrelevant downloads, and unsupported content types.
- Prevent crawl loops, duplicate URLs, query-string traps, calendar traps, and unbounded pagination.
- Validate every redirect target and ensure it remains within approved scope.
- Block private, loopback, link-local, and internal IP destinations to reduce SSRF risk.
- Respect 403, 429, and other error responses; do not attempt to bypass access restrictions.
- Record failed, blocked, skipped, low-content, duplicate, and out-of-scope pages.
- Handle pages with JavaScript-rendered content only if required; use Playwright as a documented fallback, not as an unnecessary default.
- Do not treat a temporary failure as proof that a page was deleted.

### 6.2 Content quality rules

Remove scripts, styles, tracking elements, cookie banners, empty elements, and repeated layout text where this can be done safely. Prefer semantic content containers such as `main` and `article`, with a fallback parser. Preserve useful contact details, headings, paragraphs, list structure, tables, qualifications, and context. The extractor must not invent content or silently paraphrase the page.

---

## 7. Data Ingestion and Preparation Pipeline

### 7.1 Proposed dependencies

Use Python 3.11 or newer unless the deployment environment requires another tested version. Suggested libraries:

- `requests` for HTTP retrieval.
- `beautifulsoup4` for HTML parsing.
- `urllib.parse` and `urllib.robotparser` for URL utilities and robots handling.
- `pydantic` for model/schema validation.
- `tiktoken` or a tokenizer appropriate to the selected embedding/RAG setup for chunk token counts.
- `python-dotenv` for local environment configuration.
- `pytest` for tests.
- `logging` or structured logging for operational output.
- `sentence-transformers` for local embeddings if using the recommended local embedding path.
- `chromadb` for the initial vector database option.
- `fastapi`, `uvicorn`, and the official Groq Python SDK or a compatible HTTP client for the API and LLM integration.

Pin and test dependency versions in the project configuration. Do not require a Groq or embedding API key to run the crawler and chunker.

### 7.2 Raw dataset

Primary output: `data/raw/eureka_website_data.json`.

Use a versioned JSON object with crawl statistics and a list of page records. Each record should include, when available:

- `page_id`: deterministic identifier derived from the normalized canonical/source URL.
- `title` and `meta_description`.
- `source_url`, `canonical_url`, and `final_url`.
- `headings`: ordered heading objects with level and text.
- `content`: cleaned text preserving paragraph and section boundaries.
- `content_blocks`: optional structured paragraphs, lists, and table blocks where helpful.
- `internal_links`: normalized internal URLs discovered from the page.
- `content_hash`: SHA-256 hash of normalized extracted content.
- `http_status`, `crawl_timestamp`, and extraction warnings.

The root object should include a schema version, website scope, crawl start/finish time, run ID, crawler version, and accurate statistics. Do not put placeholder/example content in the live dataset. Sample fixtures must be stored separately and clearly named.

### 7.3 Chunked dataset

Primary output: `data/processed/eureka_website_chunks.json`.

Each chunk must include:

- `chunk_id`: deterministic ID using a documented strategy.
- `page_id` and `chunk_index`.
- `source_url`, `canonical_url` if available, and `page_title`.
- `section_heading` or heading path.
- `content`: exact extracted content text, not invented text.
- `token_count`, `content_hash`, and `chunking_version`.
- Optional source `last_crawled_at` and content-type metadata.

Initial configurable chunk defaults:

- Target: approximately 500 tokens.
- Overlap: approximately 75 tokens.
- Maximum: 700 tokens.
- Minimum: 80 tokens where practical.

Tune these values through retrieval evaluation. Chunk by headings, paragraphs, list/table boundaries, and semantic sections where possible. Split long blocks only when needed. Do not combine unrelated pages or topics in one chunk. Every non-empty chunk must respect the configured maximum token limit. Token counts must be calculated with the configured tokenizer, not estimated from character count.

### 7.4 Data validation

Validate raw and chunked JSON and produce a report showing:

- JSON parse and schema validation results.
- Missing required fields and invalid source URLs.
- Duplicate page/chunk IDs and duplicate content hashes.
- Empty and suspiciously short pages/chunks.
- Over-limit chunks and unexpected token counts.
- Broken page references from chunks to raw records.
- Counts by status and failure reason.
- Crawl coverage, warnings, and whether results are complete or partial.

Write final outputs atomically: write to temporary files, validate, then replace the prior output. Preserve previous valid output if a run fails.

### 7.5 Incremental refresh

Support `full` and `incremental` run modes. Hash normalized page content to identify new, changed, unchanged, and potentially missing records. Re-chunk pages if their text changes or chunking settings change. Do not delete prior valid records because of a temporary HTTP error. Mark pages as stale/missing only after a documented verification policy. Keep checkpoints so interrupted runs can resume.

### 7.6 Crawl/chunk commands

Provide commands such as these and ensure the final README uses tested, accurate paths:

```bash
python scripts/crawl_website.py --max-pages 200
python scripts/create_chunks.py --target-tokens 500 --overlap-tokens 75
python scripts/run_pipeline.py --mode full
python scripts/run_pipeline.py --mode incremental
python scripts/validate_data.py
```

Support configurable base URL, path allow-list, exclusions, request delay, page limit, depth, timeouts, retry count, concurrency, User-Agent, tokenizer, chunk sizes, output paths, log level, and dry-run mode.

---

## 8. Embeddings and Vector Database

### 8.1 Recommended initial design

For the expected modest initial workload, use **ChromaDB with persistent storage on the backend server** as the simplest initial vector store, provided the host has durable disk space and a tested backup plan. This is a practical starting choice, not a claim that it is always the best production database. Keep database access behind the backend; the browser must never connect directly to ChromaDB.

Use a local sentence-transformer embedding model, with `sentence-transformers/all-MiniLM-L6-v2` as a configurable baseline for the initial prototype. Evaluate its retrieval quality on actual Eureka questions before sign-off. The embedding model name and model version must be configuration values. If a different embedding model is chosen, rebuild the entire index consistently.

A PostgreSQL database with `pgvector` is an acceptable alternate when the team prefers SQL, managed database backups, or metadata and vector data in one system. Do not implement both stores unless the project owner explicitly requests both; define a storage interface so the choice can be changed without rewriting the chat API.

### 8.2 Embedding requirements

- Embed each final chunk using the configured document embedding model.
- Embed every user question using the **same compatible embedding model and preprocessing** used for documents.
- Never directly compare embeddings of different dimensions/models as though they shared a vector space.
- Store `chunk_id`, `page_id`, URL, title, section heading, chunk text, content hash, embedding model name/version, and index version as metadata.
- Use an idempotent upsert strategy to avoid duplicate vectors on repeat ingestion.
- Do not regenerate embeddings for unchanged chunks unless the embedding model or preprocessing version changes.
- Set a clear process for reindexing all chunks after an embedding-model change.
- Keep vector-store credentials and file paths out of client-side code.

### 8.3 Vector collection

Use a documented collection such as `eureka_website_chunks`. Store the index in a persistent directory (for example `data/vectorstore/`) and configure the directory via environment variables. Test restart persistence, backup/restore, collection existence, and index counts.

### 8.4 Retrieval behavior

Initial retrieval settings are starting values and must be tuned against an evaluation set:

- Retrieve a configurable top-k, starting around 5–8 chunks.
- Apply metadata filters only when supported by the user's intent and data model.
- Use cosine/distance thresholds only after verifying the distance semantics of the selected database and embedding function. Do not assume a score is a probability.
- Optionally rerank candidates if basic retrieval is not good enough and the additional runtime/cost is approved.
- De-duplicate overlapping chunks and limit redundant passages from the same page.
- Return the chunk text and source metadata together so citations remain grounded in actual retrieved content.
- If the relevant context is weak, contradictory, empty, or irrelevant, return a transparent fallback instead of forcing an answer.

---

## 9. Backend Service

### 9.1 Responsibilities

Implement the chatbot backend as a Python FastAPI application. It is the only component allowed to access the vector store and Groq API. The backend must:

1. Validate incoming requests.
2. Apply size and rate limits.
3. Classify the user's query as in-scope, possibly in-scope, or out-of-scope.
4. Embed and retrieve relevant website chunks.
5. Decide whether retrieved evidence is sufficient.
6. Build the system prompt and context from retrieved content.
7. Call Groq using a model ID configured in the environment.
8. Validate/format the answer and source links.
9. Return a consistent response schema.
10. Record safe operational metrics and request IDs without logging secrets or unnecessary personal data.

### 9.2 Required API endpoints

All endpoints should be versioned under `/api/v1` unless the implementation documents a strong reason otherwise.

#### `GET /health/live`

Returns a simple liveness response, indicating that the API process is running. It should not reveal secrets or internal infrastructure details.

Example:

```json
{"status":"ok"}
```

#### `GET /health/ready`

Checks required startup dependencies such as configuration, vector-store access, and collection existence. The readiness endpoint should return an appropriate non-success status if required services are unavailable. Do not call the LLM just to answer every health check.

#### `POST /api/v1/chat`

Primary question-answering endpoint.

Example request:

```json
{
  "message": "What services does Eureka Solutions provide?",
  "session_id": "optional-random-client-session-id",
  "language": "auto"
}
```

Rules:

- `message` is required, trimmed, and subject to a configurable maximum length (initially 2,000 characters).
- Reject empty messages and unsupported payload shapes with a clear validation response.
- `session_id` is optional and must not contain personal or secret data. Do not promise persistent memory unless conversation storage is separately designed and approved.
- `language` may be `auto` or a supported language code. Initially, preserve the language of the user's query where the model can do so reliably; document the languages actually tested.

Example success response:

```json
{
  "request_id": "server-generated-request-id",
  "answer": "Eureka Solutions provides ...",
  "status": "answered",
  "sources": [
    {
      "title": "Services",
      "url": "https://eurekasolutions.in/Eureka2026/example-page/",
      "snippet": "A short excerpt that supports the answer."
    }
  ],
  "message": null
}
```

For insufficient context, return a safe fallback in `answer`, `status: "insufficient_evidence"`, and an empty or relevant `sources` array. Do not fabricate citations. Define stable status values, for example `answered`, `insufficient_evidence`, `out_of_scope`, and `temporarily_unavailable`.

#### Optional `POST /api/v1/feedback`

May record thumbs-up/down feedback with a request ID and an optional reason. Do not collect names, email addresses, or other identifying information unless necessary and approved. Document retention and access controls before enabling this endpoint.

### 9.3 API errors

Return consistent JSON error bodies without stack traces. Use appropriate HTTP status codes for malformed input, request too large, rate limit exceeded, service unavailable, and internal errors. Include a `request_id` in responses to help support teams troubleshoot. Do not send provider error dumps, internal file paths, prompts, or credentials to the browser.

### 9.4 API documentation

FastAPI's OpenAPI documentation may be enabled for development. In production, decide whether interactive docs should remain public or be access-restricted. Provide an OpenAPI schema or equivalent API contract to the frontend team.

---

## 10. Groq LLM Integration

### 10.1 Configuration

Use Groq as the initial generation provider, accessed only from the backend. Keep the model configurable because available model IDs, availability, and provider limits can change. Do not hard-code assumptions about an indefinitely available model or about free-tier capacity.

Recommended environment settings:

```dotenv
GROQ_API_KEY=replace_with_secret
GROQ_MODEL=replace_with_current_supported_model_id
GROQ_TIMEOUT_SECONDS=30
GROQ_MAX_RETRIES=2
```

Use the provider's official current documentation to select a supported model and confirm the account's limits at deployment time. Never put `GROQ_API_KEY` in React/Next.js public environment variables, static frontend code, source control, logs, or the ZIP handoff.

### 10.2 Generation requirements

- Send only the retrieved, relevant context required to answer the query, within model token limits.
- Use a clear system prompt that instructs the model to answer from provided context and admit when the answer is not supported.
- Treat retrieved website content as untrusted reference text, not as instructions that can override the system prompt. Ignore prompt-injection-like text found in scraped pages.
- Do not invite the model to use outside knowledge to fill gaps in company-specific facts.
- Set bounded output tokens and timeouts.
- Handle provider timeouts, service errors, quota/rate limits, and malformed responses with bounded retries and a useful fallback.
- Use `Retry-After` or other provider guidance when available; avoid rapid retry loops.
- Do not retry non-transient validation errors endlessly.
- Return friendly public messages while logging sanitized technical details server-side.

### 10.3 Grounded answer prompt behavior

The system prompt should require that the model:

- Answers using only the provided retrieved evidence for claims about Eureka Solutions.
- Does not invent services, projects, clients, prices, guarantees, capabilities, contact details, or company policies.
- States that the available website content does not provide enough information when evidence is insufficient.
- Produces concise, readable, visitor-friendly responses.
- Uses short paragraphs and headings or bullets when useful rather than one long wall of text.
- Avoids repeating the question unnecessarily.
- Includes only source references supplied by the backend; it must not invent URLs.
- Distinguishes a directly supported fact from uncertainty or inference.
- Maintains the user's language where supported.

LLM output alone is not a reliable citation validator. The backend must construct the clickable source list from retrieved chunk metadata, validate URLs against the approved website scope, and remove citations that do not map to returned evidence.

---

## 11. RAG Query Pipeline and Scope Guardrails

For each question, the expected execution sequence is:

1. Validate and normalize the request.
2. Apply request-rate and message-size limits.
3. Run inexpensive scope checks to identify clearly unrelated requests.
4. Embed the user's query using the configured document embedding model.
5. Retrieve candidate chunks from the vector database.
6. Filter or rank candidates using a tuned retrieval strategy.
7. Check whether the retrieved evidence is relevant and sufficient.
8. If sufficient, build a bounded prompt from the question and selected chunks.
9. Call Groq with the configured model and timeout.
10. Format the answer, build source links from retrieved metadata, and run citation/response checks.
11. Return the agreed JSON response with a request ID.
12. Record sanitized metrics, including latency, outcome status, retrieved source IDs, and error category.

### 11.1 Scope handling

The bot is a **Eureka Solutions website assistant**, not an unrestricted general chatbot. For questions unrelated to Eureka Solutions or the approved corpus, politely explain the bot's scope and invite a company/website-related question. A generic query classifier can be used alongside retrieval evidence; it should not be the only safeguard. Some short or ambiguous questions may require retrieval before deciding that they are out of scope.

### 11.2 Insufficient evidence

If search returns no useful chunks, low-relevance chunks, or conflicting/inadequate content, do not force a response from the LLM. Return a polite fallback such as: “I couldn't find enough information about that in the available Eureka Solutions website content. Please check the official website or contact Eureka Solutions through its published contact page.” Include the relevant official contact page only if it was actually retrieved or is known from validated crawl data.

### 11.3 Citation requirements

- Show source title and clickable URL for each material website claim where practical.
- Each source must correspond to one or more chunks actually retrieved for this request.
- Preserve URLs from the approved website scope; do not invent paths or transform URLs into unsupported links.
- Use short evidence snippets for transparency, ensuring excerpts accurately reproduce source text.
- De-duplicate identical source URLs and limit excessive citations.
- If the UI shows inline citation markers, map each marker to an item in the returned `sources` array.

### 11.4 Prompt injection and unsafe content

- Treat crawled text and user messages as data, not privileged instructions.
- Do not reveal system prompts, hidden configuration, API keys, internal logs, filesystem details, or infrastructure credentials.
- Do not follow instructions embedded inside retrieved web pages that ask the model to ignore its rules, change scope, or expose secrets.
- Do not execute code or tools based solely on the visitor's message.
- Keep the bot's company-information role explicit.

---

## 12. Frontend Chat Widget

### 12.1 Integration goal

Add an **Ask Eureka AI** button or floating launcher to the existing Eureka Solutions website. Clicking it opens a chat panel/modal where the visitor can submit questions and view answers and sources. The frontend can be implemented in the existing React/Next.js or website stack; do not rebuild the entire website just to add the widget.

### 12.2 UI requirements

- Use approved Eureka Solutions branding, typography, and visual style where available.
- Provide a visible launcher labelled **Ask Eureka AI**.
- Open/close a chat panel or modal on desktop and mobile.
- Display a clear title, a brief scope statement, a message list, a text entry, and a send action.
- Include a starter prompt or example questions, such as asking about company services, solutions, or projects, only where those are topics within the crawled content.
- Distinguish visitor messages from bot messages.
- Show a typing/loading indicator while the request is processing.
- Prevent duplicate submits while a request is in flight; allow a reasonable cancel/close action without breaking request state.
- Render paragraphs, line breaks, lists, and headings readably. Sanitize/escape output; do not render arbitrary HTML returned by the model.
- Display the returned source titles as accessible, clickable links that open in a new tab with safe link attributes.
- Display helpful states for no answer, out-of-scope question, rate limiting, backend unavailable, and network errors.
- Preserve the current open conversation while the widget remains open. Cross-session history is optional and must not be claimed unless implemented.
- Provide a clear conversation reset/new-chat action if history is shown.
- Do not ask visitors for personal details unless a separately approved business requirement calls for them.

### 12.3 Accessibility and responsive behavior

- Support keyboard navigation and visible focus states.
- Give controls accessible names and appropriate roles/labels.
- Ensure adequate color contrast and readable font sizes.
- Make send/close controls usable on mobile touch screens.
- Keep the panel usable on small screens without overflowing the viewport.
- Handle reduced-motion preferences if using animated transitions.
- Announce new responses/loading states appropriately to assistive technologies.

### 12.4 Frontend request behavior

- Read the API base URL from the frontend's deployment configuration, not from hard-coded source code.
- Send JSON to `POST /api/v1/chat`.
- Handle successful responses and non-2xx responses gracefully.
- Enforce a frontend character limit consistent with the backend, while keeping backend validation authoritative.
- Do not place the Groq key, vector database connection string, or privileged API credentials in client-side code.
- Never call Groq directly from the browser.
- Do not assume CORS can be fixed by disabling browser security; configure the backend for the exact production frontend origin.

### 12.5 Frontend integration handoff

The backend team must deliver the API base URL for each environment, an OpenAPI/schema document, sample request/response payloads, error-state definitions, allowed origins, and a test endpoint. The frontend team must deliver the widget source, a list of required environment variables, setup instructions, and a record of integration tests performed on staging.

---

## 13. Security, Privacy, and Abuse Prevention

- Store secrets in environment variables or the hosting provider's secret manager. Do not commit `.env` or actual API keys.
- Include only `.env.example` with placeholders in source packages.
- Configure CORS to allow only the expected development and production website origins; avoid a wildcard policy in production unless explicitly justified.
- Use HTTPS for the public website/API.
- Apply request body/message limits and per-IP/session rate limits, with proxy-aware configuration where appropriate.
- Set reasonable backend concurrency and provider request timeouts.
- Validate request schemas and normalize input before processing.
- Avoid arbitrary URL fetching based on user input; the chat endpoint should only query the established corpus.
- Keep vector-store files and database ports private; only the API service should access them.
- Prevent secrets, full prompts, and unnecessary personal data from appearing in logs.
- Establish retention and access policy before storing transcripts or feedback. Default to minimal/no persistent conversation storage unless approved.
- Keep system packages and Python dependencies patched; pin dependencies and review updates.
- Use least-privilege deployment credentials and restrict SSH, admin endpoints, and database access.
- Document backup and restore procedures for the raw data, chunked data, vector index, configuration (excluding secrets), and deployable code.
- Treat scraped site content and visitor input as untrusted data.

---

## 14. Deployment and Environment Configuration

### 14.1 Deployment shape

For a first deployment serving roughly 50 users/day, a single small VPS can be evaluated for the FastAPI service and persistent ChromaDB if CPU/RAM/disk and actual latency tests are satisfactory. This is a baseline, not a capacity guarantee. Run the crawler/indexing task separately from interactive requests when possible, and avoid rebuilding the entire index inside a user chat request.

Suggested deployment pieces:

- Public HTTPS entry point/reverse proxy.
- FastAPI application process managed by a production process manager or container runtime.
- Persistent storage for the ChromaDB index and generated crawl/index metadata.
- Environment configuration and secret storage.
- Application and reverse-proxy logs with rotation.
- Scheduled/manual crawl and reindex workflow.
- Backups and a documented rollback process.

The frontend may remain hosted with the existing website provider. Hosting the frontend and API in separate places is acceptable as long as HTTPS, CORS, and API base URL are configured correctly.

### 14.2 Example environment file

Provide `.env.example` with placeholders only, such as:

```dotenv
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
API_BASE_PATH=/api/v1
ALLOWED_ORIGINS=http://localhost:3000,https://eurekasolutions.in
GROQ_API_KEY=replace_with_secret
GROQ_MODEL=replace_with_current_supported_model_id
GROQ_TIMEOUT_SECONDS=30
GROQ_MAX_RETRIES=2
VECTOR_STORE=chroma
CHROMA_PERSIST_DIRECTORY=./data/vectorstore
CHROMA_COLLECTION=eureka_website_chunks
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
TOP_K=6
RELEVANCE_THRESHOLD=configure_after_evaluation
MAX_MESSAGE_CHARACTERS=2000
RATE_LIMIT_PER_MINUTE=configure_for_host
LOG_LEVEL=INFO
```

The actual configuration parser must define how comma-separated origins and numeric values are validated. Placeholder values must be replaced through the deployment environment, not committed to source control. If a PostgreSQL/pgvector implementation is selected instead, add a database URL via secret storage and document migrations/backup procedures.

### 14.3 Deployment stages

1. **Local development:** local crawl fixtures, mocked Groq calls, unit tests, and developer UI.
2. **Staging:** real approved website crawl, full index, staging API URL, production-like CORS, and frontend widget integration.
3. **Production:** HTTPS, real secrets, persistent storage, backups, rate limits, monitoring, and reviewed error behavior.

### 14.4 Production readiness

- API starts reliably and becomes ready only when required dependencies are available.
- Vector data persists across backend restarts.
- A tested process exists for rebuilds and rollbacks.
- Reverse proxy forwards the required headers/timeouts safely.
- No secret values are present in repository history or artifacts.
- Public errors do not disclose stack traces.
- Logs rotate and do not grow without bound.
- Backup restoration is tested, not merely documented.
- Live provider/model availability and account quotas are checked before release.

---

## 15. Performance and Reliability Requirements

The initial planning estimate is approximately 50 users per day; the actual number of questions, concurrency, prompt size, model latency, and provider limits must be measured. Do not equate daily visitors with 50 API requests exactly.

- Establish baseline median and 95th-percentile response latency in staging.
- Keep request timeouts and retries bounded.
- Avoid repeated embedding/model downloads during each request; load the selected local embedding model at startup where practical.
- Reuse initialized database clients and connection resources appropriately.
- Cache only when safe and when invalidation is defined; do not return stale answers after important content changes without a deliberate cache policy.
- Use persistent vector storage, and verify it can be backed up and restored.
- Return a predictable fallback on provider quota exhaustion, slow responses, missing index, or temporary backend failure.
- Isolate scheduled crawling/indexing from interactive chat resource usage where practical.
- Define maximum retrieved context size and model output tokens.
- Record latency for retrieval and generation separately to help diagnose bottlenecks.
- Document resource use during a realistic load test and resize the hosting plan if results require it.

---

## 16. Logging, Monitoring, and Operations

The backend should log a request ID, timestamp, high-level outcome/status, total latency, retrieval latency, generation latency, selected source IDs, and sanitized error category. Avoid storing the entire visitor message or response by default; if message logging is needed for quality review, require owner approval, define retention, redact sensitive data where possible, and limit access.

Operational monitoring should make it possible to detect:

- API process down or readiness failure.
- Vector store unavailable or index unexpectedly empty.
- Crawls failing repeatedly or yielding unusually few pages.
- Embedding/index counts changing unexpectedly.
- Groq errors, timeouts, and rate limits.
- High response latency or error rates.
- Excessive rejected/rate-limited requests.

Provide a runbook covering restart, logs, provider quota errors, vector-store restore, full reindex, crawl refresh, key rotation, and rollback.

---

## 17. Testing and Evaluation

Testing must include unit, integration, end-to-end, security, and answer-quality checks. Do not rely only on screenshots or one successful test query.

### 17.1 Crawler and data tests

- URL normalization and crawl-scope enforcement.
- Sitemap and internal-link discovery.
- Robots rules, redirects, HTTP errors, timeouts, rate limits, and retries.
- HTML extraction, heading/list/table preservation, Unicode, and duplicate content.
- Atomic writes, resumable runs, incremental update behavior, and failure recovery.
- Schema validation, stable IDs, content hashes, token counts, chunk overlap, and maximum chunk size.
- Actual raw and chunked JSON files are valid and contain real crawl results when a live crawl is claimed.

### 17.2 Embedding and retrieval tests

Create a small golden dataset of realistic questions grounded in actual site pages. For each question, define expected supporting page(s) or relevant facts. Evaluate:

- Whether the expected page/chunk appears in top-k results.
- Whether results are relevant rather than merely keyword-adjacent.
- Whether duplicates or irrelevant chunks dominate.
- Whether retrieval handles spelling variants and natural questions.
- Whether changes to chunking or embedding models improve or degrade results.

Do not use fabricated answers to represent live content. Clearly label synthetic test fixtures.

### 17.3 Backend/API tests

- Valid and invalid request schema.
- Empty and excessively long messages.
- In-scope, ambiguous, out-of-scope, and insufficient-evidence questions.
- Groq success, malformed response, timeout, 429, provider 5xx, and unavailable model.
- Vector store unavailable and empty index.
- Sources are only drawn from retrieved/approved metadata.
- Request IDs, safe errors, bounded retries, rate limits, and CORS behavior.
- No secrets appear in logs or response bodies.

Use mocked LLM calls for most automated tests; run a small, controlled smoke test against the real provider in staging when credentials and quotas are available.

### 17.4 Frontend tests

- Launcher opens/closes; widget works on desktop and mobile.
- Loading, success, empty, out-of-scope, offline, timeout, and rate-limited states.
- Keyboard operation, visible focus, accessible labels, and layout at common screen sizes.
- Sources are clickable and point to correct approved website pages.
- User text is displayed safely and model output cannot inject arbitrary HTML/script.
- Prevented duplicate submission and clear reset/new-chat behavior.

### 17.5 End-to-end answer-quality suite

Test a representative set of questions, including:

- Questions answered directly by an existing site page.
- Questions that require combining details from more than one relevant page.
- Questions with ambiguous wording.
- Questions asking about facts absent from the website.
- Clearly unrelated general-knowledge questions.
- Attempts to override chatbot instructions or request secrets.
- Questions with unsupported premises (for example, asking about a service not present in the corpus).

Acceptance requires factual answers to match source evidence, source URLs to be correct, and insufficient evidence to produce a clear fallback instead of hallucinations. Record defects and retest after prompt/retrieval changes.

---

## 18. Acceptance Criteria

The project is complete only when the relevant criteria below are demonstrated.

### 18.1 Website data pipeline

- The crawler stays within the approved URL scope and follows safe crawl rules.
- Live run results and any crawl omissions are summarized accurately.
- Raw JSON and chunked JSON are valid, versioned, and schema-checked.
- Each chunk has stable identity, source URL, page ID, title/section context, content hash, and accurate token count.
- Configured chunk size/overlap behavior is tested.
- Full and incremental modes work; transient failures do not delete valid content.
- Crawl report and logs distinguish complete versus partial runs.

### 18.2 Retrieval and backend

- The vector index can be rebuilt from the checked-in/generated chunk dataset.
- Embedding model is configured consistently for indexing and query embedding.
- `/health/live`, `/health/ready`, and `/api/v1/chat` behave according to documented contracts.
- Supported questions are answered using retrieved evidence, and citations map to actual source metadata.
- Out-of-scope or unsupported questions trigger a clear fallback.
- Provider rate limits/errors and missing vector data are handled without crashing the service.
- Secret keys are backend-only and are absent from the repository, frontend bundle, logs, and ZIP artifacts.

### 18.3 Frontend integration

- Ask Eureka AI launcher is present and functional on the approved website pages.
- Widget is responsive, accessible, and styled consistently with the website.
- It displays readable answers, correct source links, loading state, and user-friendly error/fallback states.
- API URL and allowed origins are environment-configurable.
- The browser never calls Groq directly.

### 18.4 Deployment and documentation

- A clean setup follows the README without undocumented steps.
- Staging and production environment settings are documented.
- HTTPS, CORS, request limits, rate limiting, logs, and persistent storage are configured.
- Backup, restoration, re-crawling, re-indexing, and rollback procedures are documented.
- A final test report records which tests passed and which limitations remain.

---

## 19. Required Deliverables and Handoff Package

The final handoff should include the full repository or an agreed source-code archive, plus the separate data ZIP.

### 19.1 Source repository layout (suggested)

```text
eureka-rag-chatbot/
├── frontend/                       # Widget or integration package, if owned here
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app and routes
│   │   ├── api/                    # Request/response schemas and endpoints
│   │   ├── rag/                    # Scope checks, retrieval, prompts, citations
│   │   ├── llm/                    # Groq adapter and provider error mapping
│   │   ├── embeddings/              # Embedding model wrapper
│   │   ├── vectorstore/             # Chroma adapter or pgvector adapter
│   │   ├── config.py               # Validated environment configuration
│   │   └── logging_config.py
│   ├── tests/
│   └── requirements.txt or pyproject.toml
├── crawler/
│   ├── src/                        # Discovery, fetch, extraction, cleaning
│   ├── scripts/                    # Crawl, chunk, validate, pipeline commands
│   └── tests/
├── data/
│   ├── raw/eureka_website_data.json
│   ├── processed/eureka_website_chunks.json
│   ├── reports/
│   ├── checkpoints/
│   └── vectorstore/                # Generated local index; include only if approved
├── frontend-integration/           # API contract/examples if frontend is separate
├── docs/
│   ├── API_CONTRACT.md
│   ├── DEPLOYMENT.md
│   ├── OPERATIONS_RUNBOOK.md
│   └── TEST_REPORT.md
├── tests/                           # End-to-end and quality evaluation
├── .env.example
├── .gitignore
├── README.md
└── problemStatement.md
```

The final structure may differ, but modules for crawler, RAG, API, frontend, and deployment must be clearly separated. Do not include a populated live vector-store directory in source control by default if the raw/chunked source data and reproducible index-build scripts are sufficient; if it is included in a delivery archive, document its size, provenance, and rebuild procedure.

### 19.2 Required files/artifacts

1. Complete runnable source code for the agreed scope.
2. Dependency lock/configuration files and `.env.example`.
3. `.gitignore` excluding virtual environments, caches, logs containing user data, secrets, local databases, and temporary files.
4. Crawler raw dataset: `data/raw/eureka_website_data.json`.
5. Processed chunk dataset: `data/processed/eureka_website_chunks.json`.
6. Crawl/chunking validation report and test report.
7. API contract with example payloads and errors.
8. README with setup, test, run, crawl, reindex, and troubleshooting instructions.
9. Deployment guide and operations runbook.
10. `problemStatement.md` (this specification).
11. `eureka-rag-data.zip` containing the crawler/chunker source, tests, documentation, report, and actual generated data outputs.
12. A final integration note identifying the deployed API URL for each environment, current model configuration, known limits, and unresolved issues. Do not include secrets in that note.

If the live site could not be accessed, the code may be delivered and tested with local fixtures, but the handoff must say that the real website data has not yet been crawled. Placeholder/sample records must never be presented as actual extracted content.

---

## 20. README and Developer Experience Requirements

The README must include:

- Supported Python/runtime versions.
- Installation and local run steps for crawler, index builder, backend, and frontend widget as applicable.
- Required environment variables and where to obtain/configure them, without embedding secrets.
- Commands to run tests and validations.
- How to run a live crawl within approved scope.
- How to build chunks and embeddings, create/rebuild the vector index, and launch the API.
- How to run a local chat smoke test and verify source citations.
- How to point the frontend at a local/staging/production API.
- How to refresh the website knowledge base without downtime or corrupted output.
- How to rotate the Groq key and change the model configuration.
- Known limitations, model/provider limits, troubleshooting, and safe rollback steps.

Every documented command must be tested in a clean environment. Where an operation requires live credentials or internet access, identify that requirement explicitly.

---

## 21. Coding-Agent Instructions (Codex or Similar)

The implementation team may use Codex or another coding agent, but must review and test its changes. Follow these instructions:

1. Treat this file as the source-of-truth specification. If a requirement cannot be implemented, document it as a limitation rather than silently omitting it.
2. Inspect the target website and current repository before coding; do not assume page categories or frontend framework without confirming them.
3. Produce real code and actual output files, not only explanations, mockups, or example JSON.
4. Keep live extracted data separate from fixtures and label both correctly.
5. Never fabricate page content, source URLs, counts, test outcomes, or successful deployment claims.
6. Use environment variables for secrets; add only placeholders to `.env.example`.
7. Build modular, typed, testable code with focused functions and actionable errors.
8. Write tests before or alongside implementation; tests must use fixtures/mocks and must not repeatedly hit the live website.
9. Run all available tests, validation commands, formatting/linting commands when configured, and a live crawl only within permitted limits.
10. Inspect the final ZIP contents to ensure it opens, has the required files, excludes secrets and temporary clutter, and includes the real outputs from the live run when available.
11. Report exact commands executed, counts from actual crawl/index runs, test results, known issues, and the remaining manual steps.
12. Do not claim that the frontend is deployed if only a backend or data ZIP was delivered. State each completed layer separately.

---

## 22. Final Definition of Done

The full chatbot project is ready for production review when:

- Approved website pages have been crawled and the resulting raw/chunked datasets are validated.
- Embeddings and a persistent vector index are built reproducibly from the chunk dataset.
- The FastAPI service has a documented API contract and correctly performs query validation, retrieval, grounded generation, citation creation, and fallback handling.
- The frontend widget is integrated into the existing Eureka Solutions website and works on agreed desktop/mobile breakpoints.
- Tests demonstrate grounded answers, correct citations, safe handling of unsupported questions, and graceful provider/backend failures.
- Deployment is HTTPS-protected, secrets are private, CORS is restricted, rate limits are configured, and storage/backup processes are verified.
- README, deployment docs, runbook, test report, data ZIP, and final handoff notes are complete.
- The owner has reviewed known limitations and approved production release.

A working crawler alone does **not** constitute completion of the full chatbot. Similarly, a working frontend mockup without a real backend and validated knowledge base does **not** constitute completion.

---

## 23. Reference Documentation

Use current official documentation during implementation because API details, model availability, quotas, and software interfaces can change:

- Groq API reference: https://console.groq.com/docs/api-reference
- Groq supported models: https://console.groq.com/docs/models
- Groq rate limits: https://console.groq.com/docs/rate-limits
- FastAPI CORS configuration: https://fastapi.tiangolo.com/tutorial/cors/
- Chroma persistent/client-server documentation: https://docs.trychroma.com/
- pgvector project documentation (if PostgreSQL is selected): https://github.com/pgvector/pgvector

The implementation team must verify the actual Groq model ID and account limits before staging or production deployment. Do not hard-code values copied from an old example if current provider documentation differs.

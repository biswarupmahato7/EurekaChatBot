# CORS Configuration & Network Security Notes

## 1. Overview

The Eureka RAG Chatbot backend strictly restricts browser cross-origin requests using FastAPI's `CORSMiddleware`. Only pre-approved origins are permitted to access the `/api/v1/chat` and `/health/*` endpoints.

## 2. Allowed Origins by Environment

| Environment | Allowed Origins | Config Source |
|---|---|---|
| **Local Development** | `http://localhost:3000`<br>`http://127.0.0.1:3000`<br>`http://localhost:5173`<br>`http://127.0.0.1:5173`<br>`https://eurekasolutions.in` | `.env` (`ALLOWED_ORIGINS`) |
| **Staging** | `https://staging.eurekasolutions.in`<br>`https://eurekasolutions.in` | Deployment environment variables |
| **Production** | `https://eurekasolutions.in`<br>`https://www.eurekasolutions.in` | Production secret/env manager |

## 3. Allowed Methods & Headers

- **Allowed HTTP Methods:** `GET`, `POST`, `OPTIONS`
- **Allowed Request Headers:**
  - `Content-Type: application/json`
  - `Accept: application/json`
  - `X-Request-ID` (optional correlation ID)
- **Exposed Response Headers:**
  - `X-Request-ID`
  - `Retry-After` (on HTTP 429)

## 4. Troubleshooting CORS Issues

1. **Preflight Failure (403 or missing `Access-Control-Allow-Origin`):**
   - Ensure the request `Origin` header matches one of the values in `ALLOWED_ORIGINS` exactly (including protocol and port).
   - If developing on a custom port (e.g. `http://localhost:8080`), add it to `ALLOWED_ORIGINS` in `.env` and restart the backend.
2. **Wildcard Origin Prohibition:**
   - The backend intentionally does **not** allow `*` (wildcard) origins in production to prevent malicious third-party websites from consuming the Groq inference quota.
3. **No Browser Credentials:**
   - `Access-Control-Allow-Credentials` is set to `False` by default because Phase C/D APIs do not use cookies or browser authentication sessions.

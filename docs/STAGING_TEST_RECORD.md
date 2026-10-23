# Ask Eureka AI — Staging Integration Test Record

**Date:** 2026-10-18  
**Test Suite:** Phase D Frontend Widget Integration & Staging Verification  
**Configured Target API Origin:** `http://127.0.0.1:8000` (Local Staging / Phase C Backend)  
**Frontend Origin Under Test:** `http://localhost:5173`  
**Test Executor:** Senior Frontend & Integration Engineer  

---

## 1. Automated Test Suite Summary

Executed via Vitest v5.0.5 with jsdom and React Testing Library:

```text
RUN v5.0.5 D:/Eureka Chat bot/frontend

✓ src/__tests__/urlValidator.test.ts (7 tests)
✓ src/__tests__/safeMarkdown.test.tsx (5 tests)
✓ src/__tests__/chatClient.test.ts (13 tests)
✓ src/__tests__/a11y.test.tsx (5 tests)
✓ src/__tests__/AskEurekaWidget.test.tsx (10 tests)

Test Files:  5 passed (5)
Tests:       40 passed (40)
Duration:    7.59s
Result:      PASS (100%)
```

---

## 2. Live Backend Integration Test Execution

The live FastAPI backend was started with persistent ChromaDB storage (3,796 chunks) and active Groq provider. Requests were dispatched using simulated frontend client headers including `Origin: http://localhost:5173`.

### Test Case 1: Liveness Probe (`GET /health/live`)
- **HTTP Status:** `200 OK`
- **Payload:** `{"status": "ok"}`
- **Result:** `PASS`

### Test Case 2: Readiness Probe (`GET /health/ready`)
- **HTTP Status:** `200 OK`
- **Payload:**
  ```json
  {
    "status": "ready",
    "vector_store": "ok",
    "collection": "eureka_website_chunks",
    "chunks_count": 3796
  }
  ```
- **Result:** `PASS`

### Test Case 3: Grounded Inquiry (`POST /api/v1/chat`)
- **Inquiry:** `"What ERP software does Eureka Solutions implement?"`
- **Client Origin:** `http://localhost:5173`
- **HTTP Status:** `200 OK`
- **CORS Header:** `Access-Control-Allow-Origin: http://localhost:5173`
- **Correlation ID:** `req-3cc7a51904b241f4`
- **Logical Status:** `answered`
- **Citations Count:** 5 verified sources
  1. `Enterprise ERP Solutions & Custom ERP Development | Eureka Solutions` (`https://eurekasolutions.in/Eureka2026/services/enterprise-software/enterprise-erp-solutions`)
  2. `Privacy Policy | Eureka Solutions` (`https://eurekasolutions.in/Eureka2026/privacy-policy`)
  3. `Business Process Automation Solutions | Eureka Solutions` (`https://eurekasolutions.in/Eureka2026/services/enterprise-software/business-process-automation`)
  4. `Customer & Partner Portal Development | Eureka Solutions` (`https://eurekasolutions.in/Eureka2026/services/web-mobile-applications/customer-partner-portals`)
  5. `Enterprise Software Solutions | Eureka Solutions` (`https://eurekasolutions.in/Eureka2026/services/enterprise-software`)
- **Result:** `PASS`

### Test Case 4: Out of Scope Inquiry (`POST /api/v1/chat`)
- **Inquiry:** `"How do I bake sourdough bread?"`
- **HTTP Status:** `200 OK`
- **Logical Status:** `insufficient_evidence`
- **Citations:** `[]`
- **Result:** `PASS`

### Test Case 5: Input Length Ceiling Validation (`POST /api/v1/chat`)
- **Inquiry:** 2,001 characters
- **HTTP Status:** `422 Unprocessable Entity`
- **Result:** `PASS`

---

## 3. Mock Fixtures Verification

The 10 mock scenarios were validated through `src/api/mockApi.ts`:
1. Multi-citation answer: `PASS`
2. Single-citation answer: `PASS`
3. Insufficient evidence: `PASS`
4. Out-of-scope query: `PASS`
5. Rate limit (429 with retry-after): `PASS`
6. Backend unavailable (503 with retry action): `PASS`
7. Network timeout (AbortController): `PASS`
8. Malformed or unexpected response schema: `PASS`
9. Empty citation list: `PASS`
10. Invalid citation URL neutralization: `PASS`

---

## 4. Accessibility and Interaction Checks

- **Focus Management:** Keyboard focus trapped inside open chat dialog; `Escape` key closes dialog; focus restored to launcher trigger upon closing (`PASS`).
- **Screen Reader Support:** Dialog landmark has `aria-modal="true"` and `aria-labelledby="eureka-dialog-title"`; conversation has `role="log"` and `aria-live="polite"` (`PASS`).
- **Accessible Names:** All buttons and inputs provide clear, descriptive labels and titles (`PASS`).
- **Responsive Layout:** Adaptive styling verified at 320px–480px (full sheet), 481px–768px (tablet), and >=769px (floating dialog) (`PASS`).
- **Reduced Motion:** Verified `@media (prefers-reduced-motion: reduce)` disables slide transitions and dot pulsations (`PASS`).

---

## 5. Blockers and Open Actions

- **Remote Cloud Staging Environment:** A remote staging URL (e.g. `https://staging-api.eurekasolutions.in`) has not yet been provisioned by the infrastructure team. When the remote environment is provisioned, re-verify with `VITE_EUREKA_API_BASE_URL=https://staging-api.eurekasolutions.in`.
- **Zero Blockers on Frontend Implementation:** All frontend requirements, contracts, unit tests, linting, and build tasks are completely verified.

---

## 6. Verdict

`PHASE D PASS` (Verified on local staging backend and comprehensive mock test suite).

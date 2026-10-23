# Ask Eureka AI Frontend Widget — Integration & Handoff Documentation

**Document Version:** 1.0.0  
**Phase:** Phase D — Frontend Widget  
**Target Website:** `https://eurekasolutions.in/Eureka2026/`  
**Feature Name:** Ask Eureka AI  
**Frontend Repository Path:** `d:/Eureka Chat bot/frontend/`  

---

## 1. Framework and Widget Architecture

The **Ask Eureka AI** widget is implemented as a standalone, modular React 19 + TypeScript application built using Vite 8. It adheres to modern frontend best practices, zero-vulnerability Markdown parsing, scoped CSS theming matching Eureka Solutions' design system, and full WCAG 2.1 AA accessibility compliance.

### Component Architecture

```text
AskEurekaWidget (State Container: isOpen, messages, sessionId, abortController)
├── ChatLauncher (Persistent floating trigger, aria-expanded, SVG badge)
└── ChatPanel (Modal / Drawer Dialog with focus trap & Escape listener)
    ├── ChatHeader (Branded title, AI badge, Reset button, Close button)
    ├── ScopeBanner (Informative scope statement, aria-label="Scope notice")
    ├── MessageList (Scrollable log, auto-scroll, aria-live="polite")
    │   ├── StarterQuestions (Grounded corpus topics, displayed when empty)
    │   ├── MessageItem (User bubble vs Assistant formatted response)
    │   │   ├── SafeMarkdown (Sanitized AST-based renderer without dangerouslySetInnerHTML)
    │   │   ├── CitationCard (Validated HTTPS links under eurekasolutions.in)
    │   │   └── StatusNotice (Fallback, rate-limit, and retry action banners)
    │   └── LoadingIndicator (Pulsing dots, accessible screen-reader announcement)
    └── ChatComposer (Controlled textarea, 2,000 char counter, double-submit guard)
```

### Key Architectural Safeguards
- **Zero Browser LLM Calls:** The frontend client never contacts Groq directly and never contains any Groq API credentials. All inference passes through the FastAPI backend.
- **Zero Dangerous HTML:** Model responses are converted into React elements (`<p>`, `<ul>`, `<ol>`, `<li>`, `<strong>`, `<em>`, `<code>`) without using `dangerouslySetInnerHTML`.
- **Strict Citation Validation:** URLs are verified to ensure protocol `https:` and domain `eurekasolutions.in`. Unsafe schemes (`javascript:`, `data:`, `file:`) are neutralized.
- **Strict Input Constraints:** Client enforces the backend's 2,000-character ceiling, trimming, and prevents whitespace-only submission.
- **Stale Request Cancellation:** AbortController cancels in-flight network requests on conversation reset or unmount, preventing race conditions.

---

## 2. Files Created or Changed

### Frontend Application (`frontend/`)
- `package.json` — Vite + React 19 + TypeScript + Vitest + Testing Library dependencies and scripts (`dev`, `build`, `lint`, `test`, `preview`).
- `vite.config.ts` — Vite bundler and Vitest test runner configuration.
- `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json` — TypeScript compilation configuration.
- `index.html` — Branded host HTML with title "Eureka Solutions | Ask Eureka AI Chatbot".
- `.env.example`, `.env.development`, `.env.production` — Environment variable configurations.
- `src/main.tsx` — Application entrypoint with `StrictMode`.
- `src/index.ts` — Public library exports for importing the widget into parent host apps.
- `src/index.css` — Modern CSS reset and Google Fonts ("Onest", "Inter").
- `src/App.tsx` — Branded Eureka Solutions host demo page with navigation, capability cards, and embedded widget.
- `src/setupTests.ts` — Testing environment setup with `@testing-library/jest-dom`.
- `src/api/types.ts` — TypeScript types (`ChatRequest`, `ChatResponse`, `SourceItem`, `ChatStatus`, `ChatMessage`, `ApiResult`).
- `src/api/urlValidator.ts` — Citation URL security sanitizer and origin validator.
- `src/api/mockApi.ts` — 10 fixture scenarios for offline development and testing.
- `src/api/chatClient.ts` — Typed HTTP client with fetch, 30s timeout, abort controller, and schema validation.
- `src/constants/starterQuestions.ts` — Verified starter questions grounded in crawled website corpus.
- `src/utils/safeMarkdown.tsx` — Safe markdown-to-React elements parser (zero XSS vulnerability).
- `src/styles/eureka-tokens.css` — CSS design tokens (`#0d6efd`, `#212529`, `#f8f9fa`, `#dee2e6`).
- `src/styles/eureka-widget.css` — Scoped `.eureka-` widget styles with responsive and reduced-motion rules.
- `src/components/ChatLauncher.tsx` — Floating launcher trigger.
- `src/components/ChatHeader.tsx` — Modal header with reset and close actions.
- `src/components/ScopeBanner.tsx` — Corpus scope statement.
- `src/components/StarterQuestions.tsx` — Clickable prompt chips.
- `src/components/CitationCard.tsx` — Source citation card with safe external anchor.
- `src/components/StatusNotice.tsx` — Fallback and retry action banners.
- `src/components/LoadingIndicator.tsx` — Accessible loading indicator.
- `src/components/MessageItem.tsx` — Message bubble renderer.
- `src/components/MessageList.tsx` — Scrollable conversation stream with live region.
- `src/components/ChatComposer.tsx` — Controlled input with 2,000 char counter and enter-to-send.
- `src/components/ChatPanel.tsx` — Modal dialog container with keyboard focus trap and Escape handler.
- `src/components/AskEurekaWidget.tsx` — Root state container.
- `src/__tests__/urlValidator.test.ts` — 7 unit tests for citation link security.
- `src/__tests__/safeMarkdown.test.tsx` — 5 unit tests for markdown formatting and XSS protection.
- `src/__tests__/chatClient.test.ts` — 13 unit tests for HTTP responses, errors, timeouts, and validation.
- `src/__tests__/a11y.test.tsx` — 5 accessibility tests for ARIA landmarks and keyboard controls.
- `src/__tests__/AskEurekaWidget.test.tsx` — 10 integration tests covering full user flows.

### Integration Contracts & Documentation
- `frontend-integration/README.md` — Handoff overview and quick reference.
- `frontend-integration/widget-integration-guide.md` — Step-by-step embedding guide.
- `frontend-integration/cors-config-notes.md` — CORS origin guidelines.
- `frontend-integration/sample-requests/chat_request.json` — Sample request payload.
- `frontend-integration/sample-requests/chat_response_ok.json` — Sample successful response.
- `frontend-integration/sample-requests/chat_response_fallback.json` — Sample insufficient evidence response.
- `frontend-integration/sample-requests/chat_response_outofscope.json` — Sample out-of-scope response.
- `docs/FRONTEND_INTEGRATION.md` — This master integration and handoff document.
- `docs/STAGING_TEST_RECORD.md` — Record of automated and live integration verification.

---

## 3. Environment Variables and Example Values

The client reads environment variables via Vite's `import.meta.env`:

| Variable | Type | Default | Description |
|---|---|---|---|
| `VITE_EUREKA_API_BASE_URL` | string | `http://127.0.0.1:8000` | Base URL of the FastAPI backend service (no trailing slash). |
| `VITE_MOCK_API` | boolean string | `"false"` | When set to `"true"`, uses client-side mock fixtures instead of network calls. |
| `VITE_REQUEST_TIMEOUT_MS` | number | `30000` | Client-side request timeout in milliseconds. |

Example `.env.development`:
```dotenv
VITE_EUREKA_API_BASE_URL=http://127.0.0.1:8000
VITE_MOCK_API=false
VITE_REQUEST_TIMEOUT_MS=30000
```

Example `.env.production`:
```dotenv
VITE_EUREKA_API_BASE_URL=https://api.eurekasolutions.in
VITE_MOCK_API=false
VITE_REQUEST_TIMEOUT_MS=30000
```

---

## 4. Local Development Setup

1. **Navigate to the frontend folder:**
   ```bash
   cd frontend
   ```
2. **Install dependencies:**
   ```bash
   npm install
   ```
3. **Start the local Vite development server:**
   ```bash
   npm run dev
   ```
   The demo site will be available at `http://localhost:5173/` with hot module replacement (HMR).

---

## 5. How to Run Mock Mode

Mock mode simulates the backend entirely in the browser using pre-configured fixtures matching the Phase C API contract.

To enable mock mode:
1. In `frontend/.env.development`, set:
   ```dotenv
   VITE_MOCK_API=true
   ```
2. Or pass `mockMode={true}` directly as a React prop:
   ```tsx
   <AskEurekaWidget mockMode={true} />
   ```
3. Questions will resolve immediately against the 10 built-in fixture scenarios (multi-citation, single-citation, insufficient evidence, out of scope, rate limit, service unavailable, etc.).

---

## 6. How to Configure the Real Backend URL

To connect to a live backend:
1. Ensure the backend is running (`uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`).
2. Verify that `VITE_EUREKA_API_BASE_URL` points to the backend origin:
   ```dotenv
   VITE_EUREKA_API_BASE_URL=http://127.0.0.1:8000
   ```
3. Ensure the frontend origin (`http://localhost:5173` or staging URL) is included in the backend's `ALLOWED_ORIGINS` environment variable.

---

## 7. How to Run Component and API Integration Tests

All tests are implemented using **Vitest** and **React Testing Library**:

- **Run all tests once:**
  ```bash
  cd frontend
  npm test
  ```
- **Run tests in watch mode during development:**
  ```bash
  cd frontend
  npm run test:watch
  ```
- **Run code quality linting (oxlint):**
  ```bash
  cd frontend
  npm run lint
  ```
- **Run TypeScript compilation check & production bundle build:**
  ```bash
  cd frontend
  npm run build
  ```

---

## 8. Supported Backend Statuses and UI Behavior

| Status | HTTP Code | UI Behavior | Sources Displayed |
|---|---|---|---|
| `answered` | `200 OK` | Renders formatted markdown answer with paragraph breaks, bullet lists, bold text, and clickable verified source cards. | 1 or more verified citations. |
| `insufficient_evidence` | `200 OK` | Renders polite fallback message explaining that the requested details were not found on the website. | Empty or suppressed. |
| `out_of_scope` | `200 OK` | Renders polite scope notice explaining that the assistant is dedicated to Eureka Solutions offerings. | Empty. |
| `temporarily_unavailable` | `503 Service Unavailable` | Displays danger notice with a deliberate **"Try Again"** button. Preserves user's typed message in composer. | Empty. |
| `rate_limit` | `429 Too Many Requests` | Displays rate limit notice indicating retry cooldown (e.g. 60 seconds). Send button disabled during cooldown. | Empty. |
| `validation_error` | `422 Unprocessable` | Displays user-friendly validation explanation without crashing. | Empty. |

---

## 9. Expected Citation Schema and Link Safety Rules

### Expected Schema (`SourceItem`)
```typescript
interface SourceItem {
  title: string   // Page title or section heading
  url: string     // Verified source URL
  snippet: string // Extracted excerpt supporting the answer
}
```

### Link Safety Verification
1. **Allowed Scheme:** Must strictly be `https:`.
2. **Allowed Origin:** Must strictly match `eurekasolutions.in` or `*.eurekasolutions.in`.
3. **Neutralization:** Dangerous schemes (`javascript:`, `data:`, `file:`, `vbscript:`) or untrusted external hostnames are stripped from clickable rendering.
4. **Anchor Attributes:** Rendered with `target="_blank"` and `rel="noopener noreferrer"` with an explicit accessible label (`aria-label="Source N: [Title] (opens in a new tab)"`).

---

## 10. Approved Routes and Insertion Point

The widget launcher should be embedded in the primary layout wrapper on approved public pages:
- `/` (Homepage)
- `/Eureka2026/` (Main portal)
- `/Eureka2026/services/*` (All service detail pages)
- `/Eureka2026/industries/*` (All industry sector pages)
- `/Eureka2026/case-studies/*` (Customer success stories)
- `/Eureka2026/about/` (About Eureka Solutions)

**Placement:** Fixed at `bottom: 24px; right: 24px; z-index: 99999;`. On mobile viewports (<= 480px), adapts to `bottom: 16px; right: 16px;`.

---

## 11. Accessibility and Responsive Behavior

### Accessibility (WCAG 2.1 AA)
- **Keyboard Navigation:** Tab and Shift+Tab navigate through all interactive elements (launcher, close button, reset button, starter questions, source links, textarea, send button).
- **Focus Trapping:** When the chat panel dialog is open, keyboard focus is constrained within the dialog.
- **Escape Key:** Pressing `Escape` closes the chat dialog immediately.
- **Focus Restoration:** Closing the dialog restores focus to the launcher button.
- **Screen Reader Announcements:** The conversation container has `role="log"` and `aria-live="polite"`. The loading indicator includes `<span className="eureka-sr-only">`.
- **Motion Sensitivity:** `@media (prefers-reduced-motion: reduce)` disables slide transitions and pulsating animations.

### Responsive Breakpoints
- **Mobile (<= 480px):** Chat panel adapts to full viewport bottom sheet (`width: 100vw; height: 100%; border-radius: 0;`), ensuring comfortable touch targets and visible composer.
- **Tablet (481px–768px):** Compact floating dialog (`width: 380px; height: 560px;`).
- **Desktop (>= 769px):** Standard floating dialog (`width: 410px; height: 620px;`) with smooth slide-up animation.

---

## 12. Staging Integration Procedure

1. Deploy the FastAPI backend to the staging environment (e.g. `https://staging-api.eurekasolutions.in`).
2. Add the staging frontend origin (e.g. `https://staging.eurekasolutions.in`) to the backend's `ALLOWED_ORIGINS`.
3. In the frontend staging environment, configure:
   ```dotenv
   VITE_EUREKA_API_BASE_URL=https://staging-api.eurekasolutions.in
   VITE_MOCK_API=false
   ```
4. Build the frontend production bundle (`npm run build`).
5. Execute automated test suite against the staging API or verify via `docs/STAGING_TEST_RECORD.md`.

---

## 13. Known Limitations and Unverified Behavior

- **No Multi-Turn Conversation Memory:** As per Phase C/D specifications, the backend processes each inquiry independently and does not store historical turns on the server. The client maintains in-session visual transcript only.
- **No Direct Audio/Voice Input:** Voice input is outside the Phase D scope and is not currently implemented.
- **Rate Limit Window:** Backend enforces 60 requests per minute per IP address. Client displays a 60-second cooldown notice when HTTP 429 is received.

---

## 14. Build and Release Instructions

1. **Verify all tests pass:**
   ```bash
   cd frontend
   npm test
   ```
2. **Verify zero lint errors:**
   ```bash
   npm run lint
   ```
3. **Build the production bundle:**
   ```bash
   npm run build
   ```
4. **Output artifacts:**
   - Bundled output located in `frontend/dist/`.
   - Host applications can import `AskEurekaWidget` from `src/index.ts` or embed `dist/assets/index-[hash].js` and `dist/assets/index-[hash].css`.

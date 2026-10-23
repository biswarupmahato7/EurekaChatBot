# Ask Eureka AI — Frontend Chatbot Widget

**Component:** `frontend/`  
**Framework:** React 19 + TypeScript + Vite  
**Styling:** Vanilla CSS (`eureka-widget.css`) with WCAG 2.1 AA accessible contrast and reduced-motion support  
**Testing:** Vitest v5.0.5 + Testing Library (64/64 automated tests passing)  

---

## 1. Overview & Capabilities

The **Ask Eureka AI Widget** is an embeddable, responsive chat interface designed to live on the Eureka Solutions website (`https://eurekasolutions.in/Eureka2026/`).

### Key Features
- **Responsive Layout:** Bottom-sheet mobile drawer (320px–480px), centered modal tablet card (481px–768px), and bottom-right floating launcher on desktop (>=769px).
- **Context-Aware Quick-Reply Chips:** Renders interactive, keyboard-accessible suggestion chips for ambiguous queries or contact-related workflows.
- **Hidden Internal Sources:** Preserves professional conversational presentation by suppressing internal URLs and chunk IDs from the UI, while maintaining full citation metadata in the API response.
- **Duplicate Mount Guard (UI-020):** Detects existing DOM instances and cleanly suppresses duplicate mounts if accidentally included multiple times in host templates.
- **Accessibility (a11y):** Full keyboard navigation (`Tab`, `Escape`, `Enter`, `Space`), focus trapping, screen-reader landmarks (`role="dialog"`, `role="log"`), and accessible names on all controls.
- **Safe Markdown Rendering:** Neutralizes raw HTML tags (`<script>`, `onerror=`), renders structured lists, and safely formats assistant text.

---

## 2. Directory Structure

```text
frontend/
├── src/
│   ├── api/
│   │   ├── chatClient.ts       # Robust API client with abort controller & error taxonomy
│   │   ├── mockApi.ts          # Deterministic mock scenarios for offline testing
│   │   └── types.ts            # TypeScript interfaces for API contracts
│   ├── components/
│   │   ├── AskEurekaWidget.tsx # Main floating widget container & singleton guard
│   │   ├── ChatPanel.tsx       # Message thread, composer, and header
│   │   ├── ChatComposer.tsx    # Textarea input, char counter, and send button
│   │   ├── MessageList.tsx     # Message stream with auto-scroll and live announcements
│   │   ├── MessageItem.tsx     # Message bubble, safe markdown, and quick replies
│   │   ├── QuickReplies.tsx    # Keyboard-accessible suggestion chips
│   │   └── StatusNotice.tsx    # Insufficient evidence and error notifications
│   ├── styles/
│   │   └── eureka-widget.css   # Self-contained Eureka branding CSS
│   └── __tests__/              # 64 Vitest automated test suites
├── dist/                       # Production build output (CSS & JS)
├── .env.development            # Local development environment (relative API proxy)
├── .env.production             # Production environment (points to api.eurekasolutions.in)
└── package.json
```

---

## 3. Development & Build Commands

### Install Dependencies
```bash
npm ci
```

### Start Development Server
```bash
npm run dev
```
Serves the widget demo page at `http://localhost:5173`. Proxies `/api` and `/health` requests to backend at `http://127.0.0.1:8000`.

### Run Test Suite
```bash
npm test
```
Executes all 64 unit and component test suites via Vitest and jsdom.

### Run Linting
```bash
npm run lint
```

### Production Build
```bash
npm run build
```
Type-checks with `tsc -b` and compiles bundle to `frontend/dist/`.

---

## 4. Integration into Host Web Pages

### Direct Script Tag Embed
```html
<!-- Load compiled styles -->
<link rel="stylesheet" href="/assets/index-D7GZ476g.css" />

<!-- Widget root container -->
<div id="eureka-chat-root"></div>

<!-- Load compiled JavaScript bundle -->
<script type="module" src="/assets/index-BfOknW9R.js"></script>
```

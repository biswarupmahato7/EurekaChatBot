# Ask Eureka AI — Widget Integration Guide

## 1. Introduction

The **Ask Eureka AI** widget is a React + TypeScript embeddable chatbot designed to deliver grounded answers about Eureka Solutions' software engineering, ERP, and cloud integration offerings (`https://eurekasolutions.in/Eureka2026/`).

## 2. Integration Approaches

### Approach A: Direct React / Next.js Component Integration (Recommended)

If the main Eureka Solutions website is built with React or Next.js, copy the `frontend/src/` folder or build it into a private NPM package.

```tsx
// In your global layout (e.g., app/layout.tsx or components/Layout.tsx)
import { AskEurekaWidget } from './components/AskEurekaWidget'

export function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        {/* Mount Ask Eureka AI Widget once per approved public page */}
        <AskEurekaWidget
          apiUrl={process.env.NEXT_PUBLIC_EUREKA_API_BASE_URL}
        />
      </body>
    </html>
  )
}
```

### Approach B: Standalone Script Embed (Static HTML or CMS)

When integrating into static HTML or CMS pages (such as WordPress or custom PHP templates):

1. Run the build in `frontend/`:
   ```bash
   cd frontend
   npm run build
   ```
2. Copy the resulting bundle from `frontend/dist/assets/` to your web server:
   - `index-[hash].js`
   - `index-[hash].css`
3. Include the assets in your website layout before `</body>`:
   ```html
   <!-- Load Eureka Widget CSS -->
   <link rel="stylesheet" href="/assets/eureka-chat-widget.css" />

   <!-- Mount Container -->
   <div id="eureka-chat-root"></div>

   <!-- Load Widget Script -->
   <script type="module" src="/assets/eureka-chat-widget.js"></script>
   ```

## 3. Approved Page Placement

The launcher should appear on the following approved public routes:
- Homepage (`/` or `/Eureka2026/`)
- Services (`/Eureka2026/services/*`)
- Industries (`/Eureka2026/industries/*`)
- Case Studies (`/Eureka2026/case-studies/*`)
- About Us (`/Eureka2026/about/`)

**Excluded Routes:**
- Internal administrative portals or login forms where a floating widget may obstruct form controls.

## 4. Environment Configuration

| Variable | Description | Default |
|---|---|---|
| `VITE_EUREKA_API_BASE_URL` | Base URL of the FastAPI backend | `http://127.0.0.1:8000` |
| `VITE_MOCK_API` | Set to `"true"` to enable client-side offline mock responses | `"false"` |
| `VITE_REQUEST_TIMEOUT_MS` | Request timeout in milliseconds | `30000` |

## 5. Security & Isolation Guarantee

- **Namespace Isolation:** All CSS classes use the `.eureka-` prefix and do not overwrite global tag styles.
- **No Groq in Browser:** The frontend client never contacts Groq or ChromaDB directly. No API secrets are embedded.
- **Zero Dangerous HTML:** Text is parsed and formatted using pure React nodes with zero `dangerouslySetInnerHTML`.
- **Verified Link Policy:** All citation links must match `https://eurekasolutions.in/` using the HTTPS scheme. Unsafe schemes (`javascript:`, `data:`, `file:`) and unauthorized origins are neutralized.

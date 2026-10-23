import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { AskEurekaWidget } from './components/AskEurekaWidget'

const eurekaRoot = document.getElementById('eureka-chat-root')
const defaultRoot = document.getElementById('root')

if (eurekaRoot) {
  // Embedded mode: mount only the chat widget on the host website
  createRoot(eurekaRoot).render(
    <StrictMode>
      <AskEurekaWidget
        apiUrl={typeof window !== 'undefined' ? window.__EUREKA_CONFIG__?.apiBaseUrl : undefined}
        initialOpen={typeof window !== 'undefined' ? window.__EUREKA_CONFIG__?.initialOpen : undefined}
      />
    </StrictMode>,
  )
} else if (defaultRoot) {
  // Standalone preview mode: mount the full application shell
  createRoot(defaultRoot).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
} else {
  // Fallback: auto-create container in document body
  const autoRoot = document.createElement('div')
  autoRoot.id = 'eureka-chat-root'
  document.body.appendChild(autoRoot)
  createRoot(autoRoot).render(
    <StrictMode>
      <AskEurekaWidget
        apiUrl={typeof window !== 'undefined' ? window.__EUREKA_CONFIG__?.apiBaseUrl : undefined}
        initialOpen={typeof window !== 'undefined' ? window.__EUREKA_CONFIG__?.initialOpen : undefined}
      />
    </StrictMode>,
  )
}


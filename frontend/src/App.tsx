import { useState, useEffect } from 'react'
import { AskEurekaWidget } from './components/AskEurekaWidget'
import { getApiBaseUrl } from './api/chatClient'
import './styles/eureka-tokens.css'

export function App() {
  const [backendHealth, setBackendHealth] = useState<'checking' | 'healthy' | 'offline'>('checking')
  const baseUrl = getApiBaseUrl()

  useEffect(() => {
    let isMounted = true
    fetch(`${baseUrl}/health/live`)
      .then((res) => {
        if (isMounted) {
          setBackendHealth(res.ok ? 'healthy' : 'offline')
        }
      })
      .catch(() => {
        if (isMounted) {
          setBackendHealth('offline')
        }
      })
    return () => {
      isMounted = false
    }
  }, [baseUrl])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', backgroundColor: '#fcfcfd' }}>
      {/* Eureka Solutions Branded Navigation */}
      <header
        style={{
          borderBottom: '1px solid #dee2e6',
          backgroundColor: '#ffffff',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <div
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            padding: '16px 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span
              style={{
                fontSize: '1.4rem',
                fontWeight: 800,
                color: '#0d6efd',
                letterSpacing: '-0.02em',
              }}
            >
              Eureka Solutions
            </span>
            <span
              style={{
                fontSize: '0.75rem',
                fontWeight: 600,
                backgroundColor: backendHealth === 'healthy' ? '#d1e7dd' : '#f8d7da',
                color: backendHealth === 'healthy' ? '#0f5132' : '#842029',
                padding: '3px 8px',
                borderRadius: '12px',
              }}
            >
              API: {backendHealth === 'healthy' ? 'Connected' : backendHealth === 'checking' ? 'Checking' : 'Local / Mock'}
            </span>
          </div>

          <nav style={{ display: 'flex', gap: '24px', fontSize: '0.95rem', fontWeight: 500, color: '#495057' }}>
            <a href="#services" style={{ color: 'inherit', textDecoration: 'none' }}>
              Services
            </a>
            <a href="#industries" style={{ color: 'inherit', textDecoration: 'none' }}>
              Industries
            </a>
            <a href="#case-studies" style={{ color: 'inherit', textDecoration: 'none' }}>
              Case Studies
            </a>
            <a href="#about" style={{ color: 'inherit', textDecoration: 'none' }}>
              About
            </a>
          </nav>
        </div>
      </header>

      {/* Main Content Area */}
      <main style={{ flex: 1, maxWidth: '1200px', margin: '0 auto', padding: '48px 24px', width: '100%' }}>
        {/* Hero Section */}
        <section style={{ textAlign: 'center', maxWidth: '800px', margin: '0 auto 64px auto' }}>
          <h1
            style={{
              fontSize: '2.5rem',
              fontWeight: 800,
              color: '#212529',
              lineHeight: 1.2,
              marginBottom: '16px',
            }}
          >
            Award-Winning Enterprise Software &amp; Cloud Integration
          </h1>
          <p style={{ fontSize: '1.15rem', color: '#6c757d', lineHeight: 1.6, marginBottom: '28px' }}>
            Transform your business operations with our market-leading Oracle NetSuite ERP implementations,
            Cloud Data Integration solutions, and tailored engineering services.
          </p>
        </section>

        {/* Services Grid */}
        <section id="services" style={{ marginBottom: '64px' }}>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 700, marginBottom: '24px', color: '#212529' }}>
            Core Capabilities
          </h2>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '24px',
            }}
          >
            <div style={{ backgroundColor: '#fff', border: '1px solid #dee2e6', borderRadius: '12px', padding: '24px' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#0d6efd', marginBottom: '8px' }}>
                Oracle NetSuite ERP
              </h3>
              <p style={{ color: '#495057', fontSize: '0.95rem', lineHeight: 1.5 }}>
                End-to-end cloud ERP deployment, customisation, and continuous optimisation tailored to your financial workflows.
              </p>
            </div>

            <div style={{ backgroundColor: '#fff', border: '1px solid #dee2e6', borderRadius: '12px', padding: '24px' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#0d6efd', marginBottom: '8px' }}>
                Cloud Data Integration
              </h3>
              <p style={{ color: '#495057', fontSize: '0.95rem', lineHeight: 1.5 }}>
                Seamless data pipelines connecting disparate business systems, eCommerce storefronts, and warehouse management.
              </p>
            </div>

            <div style={{ backgroundColor: '#fff', border: '1px solid #dee2e6', borderRadius: '12px', padding: '24px' }}>
              <h3 style={{ fontSize: '1.2rem', fontWeight: 600, color: '#0d6efd', marginBottom: '8px' }}>
                Banking &amp; Finance Solutions
              </h3>
              <p style={{ color: '#495057', fontSize: '0.95rem', lineHeight: 1.5 }}>
                High-compliance portals, automated auditing, and core banking integrations built with enterprise security standards.
              </p>
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer style={{ borderTop: '1px solid #dee2e6', padding: '24px', textAlign: 'center', color: '#6c757d', fontSize: '0.9rem' }}>
        &copy; 2026 Eureka Solutions. All rights reserved. Target site: https://eurekasolutions.in/Eureka2026/
      </footer>

      {/* Ask Eureka AI Widget mounted at layout level */}
      <AskEurekaWidget />
    </div>
  )
}

export default App

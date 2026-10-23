/**
 * Mock API service providing verified fixture scenarios for local development and testing.
 * Strictly mirrors the Phase C API contract.
 */
import type { ApiResult, ChatRequest } from './types'

export type MockScenario =
  | 'multi_citation'
  | 'single_citation'
  | 'insufficient_evidence'
  | 'out_of_scope'
  | 'rate_limit'
  | 'service_unavailable'
  | 'network_timeout'
  | 'malformed_response'
  | 'empty_citations'
  | 'invalid_citation_url'
  | 'contact_clarification'
  | 'help_clarification'

export const MOCK_FIXTURES: Record<MockScenario, (req: ChatRequest) => ApiResult> = {
  // 1. Successful answer with multiple valid citations
  multi_citation: () => ({
    success: true,
    data: {
      request_id: 'req-mock-multi-01',
      answer:
        'Eureka Solutions provides comprehensive enterprise software services including award-winning Oracle NetSuite ERP implementations, bespoke Cloud Data Integration, and custom web and mobile portals. Our certified specialists work across diverse sectors including Financial Services, Wholesale Distribution, and Manufacturing.',
      status: 'answered',
      sources: [
        {
          title: 'Oracle NetSuite ERP Implementation Services',
          url: 'https://eurekasolutions.in/Eureka2026/services/netsuite/',
          snippet:
            'Eureka Solutions is a multi-award-winning Oracle NetSuite Solution Provider with over 20 years of experience delivering cloud ERP implementations and customisations.',
        },
        {
          title: 'Cloud Data & Systems Integration',
          url: 'https://eurekasolutions.in/Eureka2026/services/cloud-integration/',
          snippet:
            'Our bespoke Cloud Data Integration platform synchronises ERP, CRM, and eCommerce platforms seamlessly in real time.',
        },
      ],
      message: null,
    },
  }),

  // 2. Answer with one citation
  single_citation: () => ({
    success: true,
    data: {
      request_id: 'req-mock-single-02',
      answer:
        'Eureka Solutions delivers tailored technology solutions for the Banking & Financial Services industry, focusing on compliance, regulatory reporting, and seamless system interoperability.',
      status: 'answered',
      sources: [
        {
          title: 'Banking & Financial Services Solutions',
          url: 'https://eurekasolutions.in/Eureka2026/industries/banking-finance/',
          snippet:
            'We enable financial institutions to modernise core operations, automate compliance audits, and integrate legacy systems with modern cloud infrastructure.',
        },
      ],
      message: null,
    },
  }),

  // 3. Insufficient evidence
  insufficient_evidence: () => ({
    success: true,
    data: {
      request_id: 'req-mock-insuff-03',
      answer:
        "I couldn't find enough information about that in the available Eureka Solutions website content. Please visit the official Eureka Solutions website or contact our team directly for further details.",
      status: 'insufficient_evidence',
      sources: [],
      message: null,
    },
  }),

  // 4. Out of scope
  out_of_scope: () => ({
    success: true,
    data: {
      request_id: 'req-mock-scope-04',
      answer:
        'I am the Ask Eureka AI assistant, designed specifically to answer questions about Eureka Solutions, our enterprise software services, industry solutions, and case studies. I cannot assist with inquiries outside this scope.',
      status: 'out_of_scope',
      sources: [],
      message: null,
    },
  }),

  // 5. Rate limit (429)
  rate_limit: () => ({
    success: false,
    errorType: 'rate_limit',
    message: 'Too many requests. Please wait a moment before sending another question.',
    requestId: 'req-mock-429-05',
    retryAfterSeconds: 60,
  }),

  // 6. Backend unavailable (503)
  service_unavailable: () => ({
    success: false,
    errorType: 'unavailable',
    message: 'The AI assistant service is temporarily unavailable. Please try again shortly.',
    requestId: 'req-mock-503-06',
  }),

  // 7. Network timeout
  network_timeout: () => ({
    success: false,
    errorType: 'timeout',
    message: 'Request timed out after waiting for backend response.',
  }),

  // 8. Malformed or unexpected response
  malformed_response: () => ({
    success: false,
    errorType: 'schema',
    message: 'Received an unexpected response shape from the backend.',
    requestId: 'req-mock-bad-08',
  }),

  // 9. Empty citation list
  empty_citations: () => ({
    success: true,
    data: {
      request_id: 'req-mock-empty-09',
      answer:
        'Eureka Solutions has established partnerships across technology leaders to support scalable business architecture.',
      status: 'answered',
      sources: [],
      message: null,
    },
  }),

  // 10. Invalid citation URL (should be sanitized/filtered out by the UI)
  invalid_citation_url: () => ({
    success: true,
    data: {
      request_id: 'req-mock-invalid-10',
      answer: 'Here is an answer that previously had an untrusted citation link attached.',
      status: 'answered',
      sources: [
        {
          title: 'Suspicious External Link',
          url: 'javascript:alert("XSS")',
          snippet: 'This snippet has an invalid scheme.',
        },
        {
          title: 'Legitimate Source',
          url: 'https://eurekasolutions.in/Eureka2026/about/',
          snippet: 'Eureka Solutions official about page.',
        },
      ],
      message: null,
    },
  }),

  // 11. Contact clarification with verified email and quick replies
  contact_clarification: () => ({
    success: true,
    data: {
      request_id: 'req-mock-contact-11',
      answer:
        'You can reach the Eureka Solutions team directly by emailing info@eurekasolutions.in. Our team is based in Mumbai and is happy to assist you with enterprise software, cloud integration, and technology consulting.\n\nWhat would you like to connect with the Eureka Solutions team about?',
      status: 'answered',
      sources: [],
      quick_replies: [
        'Discuss a project',
        'Ask about services',
        'Business partnership',
        'General enquiry',
        'Something else',
      ],
      message: null,
    },
  }),

  // 12. Ambiguous help clarification
  help_clarification: () => ({
    success: true,
    data: {
      request_id: 'req-mock-help-12',
      answer: 'Sure! What can I help you with?',
      status: 'answered',
      sources: [],
      quick_replies: [
        'Learn about services',
        'Discuss a project',
        'Ask about a case study',
        'Contact the team',
      ],
      message: null,
    },
  }),
}

/**
 * Dispatches a request to the mock handler based on inquiry keywords or fallback.
 */
export async function mockChatApi(
  req: ChatRequest,
  forcedScenario?: MockScenario
): Promise<ApiResult> {
  // Simulate natural network delay
  await new Promise((resolve) => setTimeout(resolve, 300))

  if (forcedScenario && MOCK_FIXTURES[forcedScenario]) {
    return MOCK_FIXTURES[forcedScenario](req)
  }

  const query = req.message.toLowerCase()

  if (query.includes('weather') || query.includes('recipe') || query.includes('football')) {
    return MOCK_FIXTURES.out_of_scope(req)
  }

  if (query.includes('1995') || query.includes('stock price') || query.includes('unknown topic')) {
    return MOCK_FIXTURES.insufficient_evidence(req)
  }

  if (query.includes('banking') || query.includes('finance')) {
    return MOCK_FIXTURES.single_citation(req)
  }

  if (query.includes('rate limit')) {
    return MOCK_FIXTURES.rate_limit(req)
  }

  if (query.includes('unavailable') || query.includes('down')) {
    return MOCK_FIXTURES.service_unavailable(req)
  }

  if (query.includes('reach out') || query.includes('contact') || query.includes('speak to')) {
    return MOCK_FIXTURES.contact_clarification(req)
  }

  if (query.includes('need help') || query.includes('help me')) {
    return MOCK_FIXTURES.help_clarification(req)
  }

  // Default to multi-citation rich answer
  return MOCK_FIXTURES.multi_citation(req)
}

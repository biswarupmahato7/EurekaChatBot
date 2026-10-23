/**
 * Eureka RAG Chatbot — Widget Public Library Entrypoint
 */
export { AskEurekaWidget } from './components/AskEurekaWidget'
export type { AskEurekaWidgetProps } from './components/AskEurekaWidget'
export { sendChatMessage, getApiBaseUrl, isMockModeEnabled } from './api/chatClient'
export { isValidCitationUrl, filterSafeSources } from './api/urlValidator'
export type {
  ChatRequest,
  ChatResponse,
  ChatStatus,
  SourceItem,
  ChatMessage,
  ApiResult,
} from './api/types'

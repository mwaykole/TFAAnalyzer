import type {
  AnalyzeRequest,
  AnalyzeResponse,
  InvestigateRequest,
  InvestigateResponse,
  HealthResponse,
} from '../types'

const API_BASE = import.meta.env.VITE_API_URL || ''

class APIError extends Error {
  constructor(public status: number, message: string) {
    super(message)
    this.name = 'APIError'
  }
}

async function request<T>(endpoint: string, options?: RequestInit & { timeout?: number }): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  const timeout = options?.timeout || 300000 // 5 minute default timeout
  
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeout)
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    })
    clearTimeout(timeoutId)

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
      throw new APIError(response.status, error.detail || error.error || 'Request failed')
    }

    return response.json()
  } catch (err) {
    clearTimeout(timeoutId)
    if (err instanceof Error && err.name === 'AbortError') {
      throw new APIError(408, 'Request timeout - analysis is taking longer than expected')
    }
    throw err
  }
}

export const api = {
  health: () => request<HealthResponse>('/health'),

  analyze: (data: AnalyzeRequest) =>
    request<AnalyzeResponse>('/api/v1/analyze', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  investigate: (data: InvestigateRequest) =>
    request<InvestigateResponse>('/api/v1/investigate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}

export { APIError }

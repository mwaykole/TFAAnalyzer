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

async function request<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }))
    throw new APIError(response.status, error.detail || error.error || 'Request failed')
  }

  return response.json()
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

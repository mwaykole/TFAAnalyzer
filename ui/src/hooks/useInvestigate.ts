import { useState } from 'react'
import { api, APIError } from '../api/client'
import type { InvestigateRequest, InvestigateResponse } from '../types'

export function useInvestigate() {
  const [data, setData] = useState<InvestigateResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const investigate = async (request: InvestigateRequest) => {
    try {
      setLoading(true)
      setError(null)
      const response = await api.investigate(request)
      setData(response)
      return response
    } catch (err) {
      const message = err instanceof APIError 
        ? err.message 
        : 'Investigation failed'
      setError(message)
      throw err
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setData(null)
    setError(null)
  }

  return { data, loading, error, investigate, reset }
}

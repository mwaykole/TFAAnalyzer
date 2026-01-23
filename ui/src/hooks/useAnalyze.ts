import { useState } from 'react'
import { api, APIError } from '../api/client'
import type { AnalyzeRequest, AnalyzeResponse } from '../types'

export function useAnalyze() {
  const [data, setData] = useState<AnalyzeResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const analyze = async (request: AnalyzeRequest) => {
    try {
      setLoading(true)
      setError(null)
      const response = await api.analyze(request)
      setData(response)
      return response
    } catch (err) {
      const message = err instanceof APIError 
        ? err.message 
        : 'Analysis failed'
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

  return { data, loading, error, analyze, reset }
}

import { useState, useEffect } from 'react'
import { api } from '../api/client'
import type { HealthResponse } from '../types'

export function useHealth() {
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchHealth = async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await api.health()
      setHealth(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch health')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHealth()
    const interval = setInterval(fetchHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  return { health, loading, error, refetch: fetchHealth }
}

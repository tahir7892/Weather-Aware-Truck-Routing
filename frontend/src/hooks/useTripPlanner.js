import { useCallback, useRef, useState } from 'react'

import { planTrip } from '../api/tripApi'

/**
 * Plans trips. Keeps the last successful trip on screen if a new request
 * fails, and ignores answers to requests that were replaced by a newer one.
 */
export function useTripPlanner() {
  const [trip, setTrip] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const controllerRef = useRef(null)

  const plan = useCallback(async (payload) => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller

    setLoading(true)
    setError(null)
    try {
      const data = await planTrip(payload, controller.signal)
      setTrip(data)
      return data
    } catch (err) {
      if (err.name !== 'AbortError') setError(err)
      return null
    } finally {
      if (controllerRef.current === controller) setLoading(false)
    }
  }, [])

  const clearError = useCallback(() => setError(null), [])

  return { trip, loading, error, plan, clearError }
}

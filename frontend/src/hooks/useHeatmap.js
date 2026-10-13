import { useCallback, useEffect, useState } from 'react'

import { getHeatmap } from '../api/tripApi'
import { prepareHeatmap } from '../utils/heatmap'

/**
 * Loads the heatmap for a planned trip in the background (after the routes
 * are already on screen) and prepares all 49 hourly frames once.
 */
export function useHeatmap(tripId) {
  const [result, setResult] = useState({ tripId: null, data: null, error: null })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!tripId) return undefined
    const controller = new AbortController()
    getHeatmap(tripId, controller.signal)
      .then((raw) => setResult({ tripId, data: prepareHeatmap(raw), error: null }))
      .catch((error) => {
        if (error.name !== 'AbortError') setResult({ tripId, data: null, error })
      })
    return () => controller.abort()
  }, [tripId, attempt])

  const retry = useCallback(() => {
    setResult({ tripId: null, data: null, error: null })
    setAttempt((n) => n + 1)
  }, [])

  // Anything stored for an older trip counts as still loading for the new one.
  const current = result.tripId === tripId
  let status = 'idle'
  if (tripId) status = !current ? 'loading' : result.error ? 'error' : 'ready'

  return {
    status,
    data: current ? result.data : null,
    error: current ? result.error : null,
    retry,
  }
}

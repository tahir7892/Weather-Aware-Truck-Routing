import { useEffect, useState } from 'react'

import './common.css'

const SLOW_AFTER_SECONDS = 12

/** Spinner shown over the results while a trip is being planned, with elapsed time. */
export default function Loader({ text = 'Checking routes and weather…' }) {
  const [seconds, setSeconds] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(timer)
  }, [])

  return (
    <div className="loader" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <b>
        {text} <span className="loader-time">{seconds}s</span>
      </b>
      <span>
        {seconds < SLOW_AFTER_SECONDS
          ? 'Finding 3 truck routes and the forecast at each checkpoint. This usually takes a few seconds.'
          : 'Still working. The routing and weather services are slow right now, so this can take a minute or more.'}
      </span>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'

import { prefersReducedMotion } from '../../utils/motion'

/** Counts smoothly from the previously shown value to `value`, then shows `format(value)`. */
export default function AnimatedNumber({ value, format = (v) => String(v), duration = 650 }) {
  const [shown, setShown] = useState(0)
  const shownRef = useRef(0)

  useEffect(() => {
    const from = shownRef.current
    if (prefersReducedMotion() || from === value) {
      shownRef.current = value
      setShown(value)
      return undefined
    }
    const start = performance.now()
    let frame
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration)
      const current = from + (value - from) * (1 - (1 - t) ** 3)
      shownRef.current = current
      setShown(current)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value, duration])

  return format(shown)
}

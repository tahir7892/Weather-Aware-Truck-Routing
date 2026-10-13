import { useEffect, useRef, useState } from 'react'

import { formatDayTime } from '../../utils/format'
import './Heatmap.css'

const MAX_HOUR = 48
const PLAY_STEP_MS = 400
const TICKS = [0, 6, 12, 18, 24, 30, 36, 42, 48]

/**
 * The 0-48 h forecast control floating at the bottom of the map: play/pause,
 * the hour slider, the heatmap on/off switch and the heatmap loading state.
 */
export default function ForecastSlider({
  hour,
  onHourChange,
  departureTime,
  heatmapStatus,
  heatmap,
  onRetry,
  showHeatmap,
  onToggleHeatmap,
}) {
  const disabled = !departureTime
  const [playing, setPlaying] = useState(false)
  const hourRef = useRef(hour)
  useEffect(() => {
    hourRef.current = hour
  }, [hour])

  useEffect(() => {
    if (!playing || disabled) return undefined
    const timer = setInterval(() => {
      onHourChange(hourRef.current >= MAX_HOUR ? 0 : hourRef.current + 1)
    }, PLAY_STEP_MS)
    return () => clearInterval(timer)
  }, [playing, disabled, onHourChange])

  const moment = departureTime ? new Date(new Date(departureTime).getTime() + hour * 3600e3) : null
  const fill = `${(hour / MAX_HOUR) * 100}%`

  return (
    <section className="timeline" aria-label="Weather forecast timeline">
      <div className="tl-top">
        <button
          type="button"
          className="play"
          onClick={() => setPlaying((p) => !p)}
          disabled={disabled}
          aria-label={playing ? 'Pause forecast' : 'Play forecast'}
          title={playing ? 'Pause' : 'Play the next 48 hours'}
        >
          {playing && !disabled ? (
            <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
              <path fill="currentColor" d="M6 4h4v16H6zM14 4h4v16h-4z" />
            </svg>
          ) : (
            <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
              <path fill="currentColor" d="M7 4l13 8-13 8z" />
            </svg>
          )}
        </button>

        <div className="tl-title">
          Weather forecast
          <small>
            {heatmapStatus === 'loading' && (
              <>
                <span className="spinner small" aria-hidden="true" /> Loading weather along the route…
              </>
            )}
            {heatmapStatus === 'error' && (
              <>
                Weather grid unavailable.{' '}
                <button type="button" className="link" onClick={onRetry}>
                  Retry
                </button>
              </>
            )}
            {heatmapStatus === 'ready' && `Heatmap within ${heatmap.corridorMiles} mi of the routes`}
            {heatmapStatus === 'idle' && 'Plan a trip to see the next 48 hours'}
          </small>
        </div>

        <label className="toggle">
          <input type="checkbox" checked={showHeatmap} onChange={(event) => onToggleHeatmap(event.target.checked)} />
          Heatmap
        </label>

        <span className="hour-label" aria-live="polite">
          {moment ? (
            <>
              <b>{hour === 0 ? 'Departure' : `+${hour} h`}</b> · {formatDayTime(moment)}
            </>
          ) : (
            '—'
          )}
        </span>
      </div>

      <input
        type="range"
        className="hour-slider"
        min="0"
        max={MAX_HOUR}
        step="1"
        value={hour}
        disabled={disabled}
        onChange={(event) => onHourChange(Number(event.target.value))}
        style={{ '--fill': fill }}
        aria-label="Hours after departure"
        aria-valuetext={moment ? `${hour} hours after departure, ${formatDayTime(moment)}` : undefined}
      />
      <div className="ticks" aria-hidden="true">
        {TICKS.map((tick) => (
          <span key={tick}>{tick === 0 ? '0 h' : tick === MAX_HOUR ? `${tick} h` : tick}</span>
        ))}
      </div>
    </section>
  )
}

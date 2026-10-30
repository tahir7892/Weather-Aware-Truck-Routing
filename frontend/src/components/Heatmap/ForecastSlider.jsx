import { useEffect, useRef } from 'react'

import { formatDayTime } from '../../utils/format'
import { HEATMAP_VIEWS, RISK_LEVELS } from '../../utils/risk'
import './Heatmap.css'

const MAX_HOUR = 48
const PLAY_STEP_MS = 400
const TICKS = [0, 6, 12, 18, 24, 30, 36, 42, 48]

/**
 * The 0-48 h forecast control floating at the bottom of the map: play/pause,
 * the hour slider, what the heatmap shows (risk / wind / rain / snow) with its
 * legend, and the heatmap on/off switch.
 */
export default function ForecastSlider({
  hour,
  onHourChange,
  playing,
  onPlayingChange,
  departureTime,
  heatmapStatus,
  heatmap,
  onRetry,
  showHeatmap,
  onToggleHeatmap,
  view,
  onViewChange,
}) {
  const disabled = !departureTime
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
  const activeView = HEATMAP_VIEWS.find((v) => v.id === view) ?? HEATMAP_VIEWS[0]
  const isPlaying = playing && !disabled

  return (
    <section className="timeline" aria-label="Weather forecast timeline">
      <div className="tl-top">
        <button
          type="button"
          className="play"
          onClick={() => onPlayingChange(!playing)}
          disabled={disabled}
          aria-label={isPlaying ? 'Pause forecast' : 'Play forecast'}
          title={isPlaying ? 'Pause (Space)' : 'Play the next 48 hours (Space)'}
        >
          {isPlaying ? (
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

      <div className={`tl-views ${showHeatmap ? '' : 'is-off'}`}>
        <div className="view-switch" role="group" aria-label="What the heatmap shows">
          {HEATMAP_VIEWS.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={option.id === activeView.id}
              onClick={() => {
                onViewChange(option.id)
                if (!showHeatmap) onToggleHeatmap(true)
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="view-legend" title={activeView.title}>
          {RISK_LEVELS.map((level, i) => (
            <span key={level.label}>
              <span className="swatch" style={{ background: level.color, opacity: i === 0 ? 0.35 : 1 }} />
              {activeView.ranges[i]}
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

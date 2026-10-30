import { useState } from 'react'

import { useElementWidth } from '../../hooks/useElementWidth'
import { formatNumber, formatTime } from '../../utils/format'
import { mileAtTime, momentAtHour } from '../../utils/geo'
import { NO_DATA, RISK_LEVELS, riskByLabel } from '../../utils/risk'
import './Routes.css'

// One small chart per condition (different units, so never a shared y-axis).
// Band edges are the same thresholds the backend uses.
const METRICS = [
  { key: 'wind', title: 'Wind', unit: 'mph', digits: 0, steps: [25, 35, 45, 55], minTop: 40, value: (c) => c.weather.wind_mph, level: (c) => c.risk.wind },
  { key: 'rain', title: 'Rain', unit: 'in/hr', digits: 2, steps: [0.1, 0.25, 0.5, 1.0], minTop: 0.3, value: (c) => c.weather.rain_in_per_hr, level: (c) => c.risk.rain },
  { key: 'snow', title: 'Snow', unit: 'in/hr', digits: 2, steps: [0.5, 1, 2, 3], minTop: 0.8, value: (c) => c.weather.snow_in_per_hr, level: (c) => c.risk.snow, optional: true },
]

const PLOT_HEIGHT = 74
const PAD = { left: 34, right: 66, top: 8 }

function MetricChart({ metric, checkpoints, width, totalMiles, hoverIndex, onHover, onPick, truckMile, showAxis }) {
  const bottom = showAxis ? 20 : 6
  const height = PAD.top + PLOT_HEIGHT + bottom
  const plotWidth = width - PAD.left - PAD.right
  const values = checkpoints.map(metric.value)
  const known = values.filter((v) => v !== null && v !== undefined)
  const top = Math.max(metric.minTop, (known.length ? Math.max(...known) : 0) * 1.15)

  const x = (mile) => PAD.left + (mile / totalMiles) * plotWidth
  const y = (value) => PAD.top + (1 - Math.min(value, top) / top) * PLOT_HEIGHT

  // Line through the checkpoints, broken where a value is missing.
  let path = ''
  checkpoints.forEach((checkpoint, i) => {
    const value = values[i]
    if (value === null || value === undefined) return
    const previousMissing = i === 0 || values[i - 1] === null || values[i - 1] === undefined
    path += `${previousMissing ? 'M' : 'L'}${x(checkpoint.mile).toFixed(1)},${y(value).toFixed(1)}`
  })

  // Shaded risk bands (Moderate and up) that fall inside the visible range.
  const bands = RISK_LEVELS.slice(1)
    .map((level, i) => ({ level, from: metric.steps[i], to: metric.steps[i + 1] ?? Infinity }))
    .filter((band) => band.from < top)

  function handleMove(event) {
    const box = event.currentTarget.getBoundingClientRect()
    const mile = ((event.clientX - box.left) / box.width) * totalMiles
    let nearest = 0
    checkpoints.forEach((checkpoint, i) => {
      if (Math.abs(checkpoint.mile - mile) < Math.abs(checkpoints[nearest].mile - mile)) nearest = i
    })
    onHover(nearest)
  }

  const peak = known.length ? Math.max(...known) : null

  return (
    <svg
      className="profile-chart"
      width={width}
      height={height}
      role="img"
      aria-label={`${metric.title} along the route${peak === null ? '' : `, highest ${formatNumber(peak, metric.digits)} ${metric.unit}`}`}
    >
      <text className="profile-title" x={PAD.left} y={PAD.top + 10}>
        {metric.title} <tspan className="profile-unit">({metric.unit})</tspan>
      </text>

      {bands.map((band) => {
        const yTop = y(Math.min(band.to, top))
        const yBottom = y(band.from)
        return (
          <g key={band.level.label}>
            <rect x={PAD.left} y={yTop} width={plotWidth} height={yBottom - yTop} fill={band.level.color} opacity="0.09" />
            <line className="profile-threshold" x1={PAD.left} x2={PAD.left + plotWidth} y1={yBottom} y2={yBottom} />
            <text className="profile-tick" x={PAD.left - 5} y={yBottom + 3} textAnchor="end">
              {band.from}
            </text>
            {yBottom - yTop >= 10 && (
              <text className="profile-band" x={PAD.left + plotWidth + 6} y={(yTop + yBottom) / 2 + 3}>
                {band.level.label}
              </text>
            )}
          </g>
        )
      })}

      <line className="profile-baseline" x1={PAD.left} x2={PAD.left + plotWidth} y1={y(0)} y2={y(0)} />
      <text className="profile-tick" x={PAD.left - 5} y={y(0) + 3} textAnchor="end">
        0
      </text>

      {truckMile !== null && (
        <line className="profile-truck" x1={x(truckMile)} x2={x(truckMile)} y1={PAD.top} y2={PAD.top + PLOT_HEIGHT} />
      )}
      {hoverIndex !== null && (
        <line className="profile-cross" x1={x(checkpoints[hoverIndex].mile)} x2={x(checkpoints[hoverIndex].mile)} y1={PAD.top} y2={PAD.top + PLOT_HEIGHT} />
      )}

      <path className="profile-line" d={path} />
      {checkpoints.map((checkpoint, i) =>
        values[i] === null || values[i] === undefined ? null : (
          <circle
            key={checkpoint.index}
            className="profile-dot"
            cx={x(checkpoint.mile)}
            cy={y(values[i])}
            r={i === hoverIndex ? 5.5 : 3.5}
            fill={(metric.level(checkpoint) ? riskByLabel(metric.level(checkpoint)) : NO_DATA).color}
          />
        ),
      )}

      {showAxis &&
        [0, 0.25, 0.5, 0.75, 1].map((f) => (
          <text
            key={f}
            className="profile-tick"
            x={x(totalMiles * f)}
            y={PAD.top + PLOT_HEIGHT + 15}
            textAnchor={f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}
          >
            {Math.round(totalMiles * f)}
            {f === 1 ? ' mi' : ''}
          </text>
        ))}

      {/* Wide invisible hit area for hover and click. */}
      <rect
        x={PAD.left}
        y={PAD.top}
        width={plotWidth}
        height={PLOT_HEIGHT}
        fill="transparent"
        style={{ cursor: 'pointer' }}
        onMouseMove={handleMove}
        onMouseLeave={() => onHover(null)}
        onClick={() => hoverIndex !== null && onPick(hoverIndex)}
      />
    </svg>
  )
}

/**
 * Wind and rain (and snow, when any is forecast) along the selected route, at
 * the time the truck reaches each checkpoint, with the risk thresholds shaded.
 */
export default function RouteProfile({ route, departureTime, hour, onHoverPoint, onShowCheckpoint }) {
  const [bodyRef, width] = useElementWidth()
  const [hoverIndex, setHoverIndex] = useState(null)
  const { checkpoints } = route
  const totalMiles = checkpoints[checkpoints.length - 1].mile || 1
  const truckMile = hour > 0 ? mileAtTime(route, momentAtHour(departureTime, hour)).mile : null

  const metrics = METRICS.filter(
    (metric) => !metric.optional || checkpoints.some((c) => (metric.value(c) ?? 0) > 0),
  )
  const hovered = hoverIndex === null ? null : checkpoints[hoverIndex]

  function hover(index) {
    setHoverIndex(index)
    const checkpoint = index === null ? null : checkpoints[index]
    onHoverPoint(checkpoint && { lat: checkpoint.lat, lon: checkpoint.lon })
  }

  return (
    <section className="card profile-card">
      <h2 className="card-title">
        Weather along Route {route.id}
        <span className="table-sub">at the time the truck reaches each point · shaded bands are the risk levels</span>
      </h2>

      <p className="profile-readout" aria-live="polite">
        {hovered ? (
          <>
            <b>Mile {formatNumber(hovered.mile)}</b> · arrives {formatTime(hovered.eta)} · wind{' '}
            {formatNumber(hovered.weather.wind_mph)} mph · rain {formatNumber(hovered.weather.rain_in_per_hr, 2)} ·{' '}
            <span className="risk-badge">
              <span className="risk-dot" style={{ background: riskByLabel(hovered.risk.level).color }} />
              {hovered.risk.level}
            </span>
          </>
        ) : (
          <span className="muted-text">Hover the chart to find a point on the map; click to open its details.</span>
        )}
      </p>

      <div ref={bodyRef} className="profile-body">
        {width > 0 &&
          metrics.map((metric, i) => (
            <MetricChart
              key={metric.key}
              metric={metric}
              checkpoints={checkpoints}
              width={width}
              totalMiles={totalMiles}
              hoverIndex={hoverIndex}
              onHover={hover}
              onPick={(index) => onShowCheckpoint(route.id, checkpoints[index].index)}
              truckMile={truckMile}
              showAxis={i === metrics.length - 1}
            />
          ))}
      </div>
    </section>
  )
}

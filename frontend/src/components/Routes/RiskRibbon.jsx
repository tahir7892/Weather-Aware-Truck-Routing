import { useState } from 'react'
import { createPortal } from 'react-dom'

import { formatTime } from '../../utils/format'
import { NO_DATA, riskByScore } from '../../utils/risk'

/** The worse of two checkpoint risk scores, ignoring missing ones (null if both are missing). */
function stretchScore(a, b) {
  const known = [a.risk.score, b.risk.score].filter((score) => score !== null && score !== undefined)
  return known.length ? Math.max(...known) : null
}

/**
 * Risk along one route, in driving order: one colored piece per stretch
 * between two checkpoints. All routes share one mile scale (`maxMiles`), so a
 * longer route has a longer ribbon. Hovering a piece marks it on the map;
 * clicking opens the checkpoint at its riskier end.
 */
export default function RiskRibbon({ route, maxMiles, truckMile, onHoverPoint, onShowCheckpoint }) {
  const [tip, setTip] = useState(null)
  const { checkpoints } = route

  const stretches = checkpoints.slice(1).map((end, i) => {
    const start = checkpoints[i]
    const score = stretchScore(start, end)
    const worst = (end.risk.score ?? -1) >= (start.risk.score ?? -1) ? end : start
    return { start, end, worst, level: score === null ? NO_DATA : riskByScore(score) }
  })

  function show(event, stretch) {
    setTip({ x: event.clientX, y: event.clientY, stretch })
    onHoverPoint({ lat: (stretch.start.lat + stretch.end.lat) / 2, lon: (stretch.start.lon + stretch.end.lon) / 2 })
  }

  function hide() {
    setTip(null)
    onHoverPoint(null)
  }

  return (
    <div className="ribbon" aria-hidden="true">
      <div className="ribbon-track">
        {stretches.map((stretch) => (
          <span
            key={stretch.end.index}
            className="ribbon-seg"
            style={{ width: `${((stretch.end.mile - stretch.start.mile) / maxMiles) * 100}%`, background: stretch.level.color }}
            onMouseEnter={(event) => show(event, stretch)}
            onMouseMove={(event) => setTip((current) => current && { ...current, x: event.clientX, y: event.clientY })}
            onMouseLeave={hide}
            onClick={(event) => {
              event.stopPropagation()
              hide()
              onShowCheckpoint(route.id, stretch.worst.index)
            }}
          />
        ))}
        {truckMile !== null && (
          <span className="ribbon-truck" style={{ left: `${(truckMile / maxMiles) * 100}%` }} title="Truck at the selected hour" />
        )}
      </div>

      {/* Rendered on <body> so the card's entry animation can't offset the tooltip. */}
      {tip && createPortal(
        <div className="ribbon-tip" style={{ left: tip.x + 14, top: tip.y - 12 }}>
          <b>
            Route {route.id} · mile {Math.round(tip.stretch.start.mile)}–{Math.round(tip.stretch.end.mile)}
          </b>
          <span>
            {formatTime(tip.stretch.start.eta)} – {formatTime(tip.stretch.end.eta)}
          </span>
          <span className="ribbon-tip-level">
            <span className="risk-dot" style={{ background: tip.stretch.level.color }} />
            {tip.stretch.level.label}
          </span>
          <small>{tip.stretch.worst.risk.reason}</small>
        </div>,
        document.body,
      )}
    </div>
  )
}

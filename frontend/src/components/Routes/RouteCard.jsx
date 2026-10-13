import { formatDuration, formatMiles, formatNumber, formatTime } from '../../utils/format'
import { MILES_BY_LEVEL_ORDER, riskByLabel } from '../../utils/risk'

/** One route's summary: distance, drive time, arrival and miles at each risk level. */
export default function RouteCard({ route, selected, onSelect }) {
  const { summary } = route
  const segments = MILES_BY_LEVEL_ORDER.map((label) => ({
    label,
    miles: summary.miles_by_level[label] ?? 0,
    color: riskByLabel(label).color,
  })).filter((segment) => segment.miles > 0)

  const riskText = segments.map((s) => `${s.label} ${formatMiles(s.miles, 0)}`).join(', ')

  return (
    <button
      type="button"
      className={`route-card ${selected ? 'is-selected' : ''}`}
      onClick={() => onSelect(route.id)}
      aria-pressed={selected}
    >
      <div className="rc-head">
        <span className="rc-letter">{route.id}</span>
        <div className="rc-name">
          <div className="rc-title">
            Route {route.id}
            {route.is_recommended && <span className="rc-badge">Recommended</span>}
          </div>
          <div className="rc-via">{route.via ? `via ${route.via}` : 'Truck route'}</div>
        </div>
        <span className="rc-rank" title="Rank (1 = best)">
          #{route.rank}
        </span>
      </div>

      <div className="rc-stats">
        <div>
          <span>Distance</span>
          <b>{formatMiles(summary.distance_miles)}</b>
        </div>
        <div>
          <span>Drive time</span>
          <b>{formatDuration(summary.duration_minutes)}</b>
        </div>
        <div>
          <span>Arrives</span>
          <b>{formatTime(summary.arrival_time)}</b>
        </div>
      </div>

      <div className="riskbar" role="img" aria-label={`Miles by risk level: ${riskText}`}>
        {segments.map((segment) => (
          <span
            key={segment.label}
            className="seg"
            style={{ flexGrow: segment.miles, background: segment.color }}
            title={`${segment.label}: ${formatMiles(segment.miles)}`}
          />
        ))}
      </div>

      <div className="rc-foot">
        <span>
          No Travel <b>{formatMiles(summary.miles_by_level['No Travel'] ?? 0, 0)}</b>
        </span>
        <span>
          Severe <b>{formatMiles(summary.miles_by_level.Severe ?? 0, 0)}</b>
        </span>
        <span>
          High <b>{formatMiles(summary.miles_by_level.High ?? 0, 0)}</b>
        </span>
        <span>
          Avg risk <b>{formatNumber(summary.average_risk, 2)}</b>
        </span>
      </div>
    </button>
  )
}

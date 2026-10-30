import { formatDuration, formatMiles, formatNumber, formatTime } from '../../utils/format'
import AnimatedNumber from '../common/AnimatedNumber'
import RiskRibbon from './RiskRibbon'

/**
 * One route's summary: distance, drive time, arrival, risk along the way and
 * the miles that decide the ranking. Hovering the card highlights the route
 * on the map; clicking selects it everywhere.
 */
export default function RouteCard({
  route,
  index,
  selected,
  hovered,
  maxMiles,
  truckMile,
  onSelect,
  onHover,
  onHoverPoint,
  onShowCheckpoint,
}) {
  const { summary } = route
  const milesAt = (label) => summary.miles_by_level[label] ?? 0

  return (
    <button
      type="button"
      className={`route-card ${selected ? 'is-selected' : ''} ${hovered && !selected ? 'is-hovered' : ''}`}
      style={{ '--i': index }}
      onClick={() => onSelect(route.id)}
      onMouseEnter={() => onHover(route.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(route.id)}
      onBlur={() => onHover(null)}
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
          <b>
            <AnimatedNumber value={summary.distance_miles} format={(v) => formatMiles(v)} />
          </b>
        </div>
        <div>
          <span>Drive time</span>
          <b>
            <AnimatedNumber value={summary.duration_minutes} format={formatDuration} />
          </b>
        </div>
        <div>
          <span>Arrives</span>
          <b>{formatTime(summary.arrival_time)}</b>
        </div>
      </div>

      <RiskRibbon
        route={route}
        maxMiles={maxMiles}
        truckMile={truckMile}
        onHoverPoint={onHoverPoint}
        onShowCheckpoint={onShowCheckpoint}
      />

      <div className="rc-foot">
        <span>
          No Travel <b>{formatMiles(milesAt('No Travel'), 0)}</b>
        </span>
        <span>
          Severe <b>{formatMiles(milesAt('Severe'), 0)}</b>
        </span>
        <span>
          High <b>{formatMiles(milesAt('High'), 0)}</b>
        </span>
        <span>
          Avg risk{' '}
          <b>
            {summary.average_risk === null ? (
              formatNumber(null)
            ) : (
              <AnimatedNumber value={summary.average_risk} format={(v) => formatNumber(v, 2)} />
            )}
          </b>
        </span>
      </div>
    </button>
  )
}

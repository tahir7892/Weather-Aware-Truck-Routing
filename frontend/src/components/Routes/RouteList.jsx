import { mileAtTime, momentAtHour } from '../../utils/geo'
import RouteCard from './RouteCard'
import './Routes.css'

/**
 * The route cards, best first. All risk ribbons share one mile scale and show
 * where each truck is at the slider's hour.
 */
export default function RouteList({
  routes,
  departureTime,
  hour,
  selectedRouteId,
  hoveredRouteId,
  onSelect,
  onHover,
  onHoverPoint,
  onShowCheckpoint,
}) {
  const ranked = [...routes].sort((a, b) => a.rank - b.rank)
  const maxMiles = Math.max(...routes.map((route) => route.checkpoints[route.checkpoints.length - 1].mile))
  const moment = momentAtHour(departureTime, hour)

  return (
    <section className="route-list" aria-label="Route options">
      {ranked.map((route, index) => (
        <RouteCard
          key={route.id}
          route={route}
          index={index}
          selected={route.id === selectedRouteId}
          hovered={route.id === hoveredRouteId}
          maxMiles={maxMiles}
          truckMile={hour > 0 ? mileAtTime(route, moment).mile : null}
          onSelect={onSelect}
          onHover={onHover}
          onHoverPoint={onHoverPoint}
          onShowCheckpoint={onShowCheckpoint}
        />
      ))}
    </section>
  )
}

import RouteCard from './RouteCard'
import './Routes.css'

/** The route cards, best first. Clicking a card selects that route everywhere. */
export default function RouteList({ routes, selectedRouteId, onSelect }) {
  const ranked = [...routes].sort((a, b) => a.rank - b.rank)

  return (
    <section className="route-list" aria-label="Route options">
      {ranked.map((route) => (
        <RouteCard key={route.id} route={route} selected={route.id === selectedRouteId} onSelect={onSelect} />
      ))}
    </section>
  )
}

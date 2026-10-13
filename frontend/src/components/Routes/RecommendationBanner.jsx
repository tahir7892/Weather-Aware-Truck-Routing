import './Routes.css'

/** Green banner with the recommended route and the backend's reason. */
export default function RecommendationBanner({ trip }) {
  const best = trip.routes.find((route) => route.id === trip.recommendation.route_id)

  return (
    <section className="recommendation" aria-live="polite">
      <div className="rec-icon" aria-hidden="true">
        ✓
      </div>
      <div>
        <h2 className="rec-title">
          Route {best.id} recommended {best.via && <span className="rec-via">via {best.via}</span>}
        </h2>
        <p className="rec-reason">{trip.recommendation.reason}</p>
      </div>
    </section>
  )
}

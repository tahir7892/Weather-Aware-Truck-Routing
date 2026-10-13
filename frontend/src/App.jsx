import { lazy, Suspense, useCallback, useState } from 'react'

import ErrorMessage from './components/common/ErrorMessage'
import Loader from './components/common/Loader'
import Warnings from './components/common/Warnings'
import ForecastSlider from './components/Heatmap/ForecastSlider'
import CheckpointTable from './components/Routes/CheckpointTable'
import RecommendationBanner from './components/Routes/RecommendationBanner'
import RouteList from './components/Routes/RouteList'
import TripForm from './components/TripForm/TripForm'
import { useHeatmap } from './hooks/useHeatmap'
import { useTripPlanner } from './hooks/useTripPlanner'
import { timeZoneName } from './utils/format'
import './App.css'

// The map library is large, so it loads in its own file while the form is already usable.
const TripMap = lazy(() => import('./components/Map/TripMap'))

const TRUCK_ICON = (
  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
    <path
      fill="currentColor"
      d="M3 6h11v9H3zM14 9h4l3 3v3h-7zM6.5 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zm11 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z"
    />
  </svg>
)

function EmptyState() {
  return (
    <section className="card empty-state">
      <h2>Find the safest way there</h2>
      <p>Enter a trip above. We will:</p>
      <ul>
        <li>find 3 truck routes,</li>
        <li>check the weather every 10, 25 or 50 miles, for the time the truck gets there,</li>
        <li>rate wind, rain and snow risk for your load, and</li>
        <li>recommend the safest route, then the fastest.</li>
      </ul>
    </section>
  )
}

export default function App() {
  const { trip, loading, error, plan, clearError } = useTripPlanner()
  const heatmap = useHeatmap(trip?.trip_id)
  const [selectedRouteId, setSelectedRouteId] = useState(null)
  const [hour, setHour] = useState(0)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [focusCheckpoint, setFocusCheckpoint] = useState(null)
  const [lastPayload, setLastPayload] = useState(null)

  const handlePlan = useCallback(
    async (payload) => {
      setLastPayload(payload)
      const result = await plan(payload)
      if (result) {
        setSelectedRouteId(result.recommendation.route_id)
        setHour(0)
        setFocusCheckpoint(null)
      }
    },
    [plan],
  )

  const selectedRoute = trip?.routes.find((route) => route.id === selectedRouteId)
  const formErrors = error?.code === 'invalid_input' ? error.fields : null

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo">{TRUCK_ICON}</div>
        <h1>Weather-Aware Truck Routing</h1>
        <span className="topbar-sub">Safest route by weather, load and travel time</span>
        <span className="topbar-tz" title="All times are shown in your own time zone">
          Times in {timeZoneName()}
        </span>
      </header>

      <div className="main">
        <aside className="sidebar">
          <TripForm onSubmit={handlePlan} onEdit={error ? clearError : undefined} loading={loading} serverErrors={formErrors} />

          <div className={`results ${loading ? 'is-loading' : ''}`}>
            {loading && <Loader />}
            {error && (
              <ErrorMessage
                error={error}
                onRetry={error.code === 'invalid_input' || !lastPayload ? undefined : () => handlePlan(lastPayload)}
                onDismiss={clearError}
              />
            )}

            {trip ? (
              <>
                <RecommendationBanner trip={trip} />
                <Warnings warnings={trip.warnings} />
                <RouteList routes={trip.routes} selectedRouteId={selectedRouteId} onSelect={setSelectedRouteId} />
                {selectedRoute && (
                  <CheckpointTable
                    route={selectedRoute}
                    interval={trip.checkpoint_interval_miles}
                    onShowCheckpoint={(index) => setFocusCheckpoint({ routeId: selectedRoute.id, index })}
                  />
                )}
              </>
            ) : (
              !loading && <EmptyState />
            )}
          </div>
        </aside>

        <section className="map-wrap">
          <Suspense fallback={<div className="map-loading">Loading map…</div>}>
            <TripMap
              trip={trip}
              selectedRouteId={selectedRouteId}
              onSelectRoute={setSelectedRouteId}
              hour={hour}
              heatmap={heatmap.data}
              showHeatmap={showHeatmap}
              focusCheckpoint={focusCheckpoint}
            />
          </Suspense>
          <ForecastSlider
            hour={hour}
            onHourChange={setHour}
            departureTime={trip?.departure_time}
            heatmapStatus={heatmap.status}
            heatmap={heatmap.data}
            onRetry={heatmap.retry}
            showHeatmap={showHeatmap}
            onToggleHeatmap={setShowHeatmap}
          />
        </section>
      </div>
    </div>
  )
}

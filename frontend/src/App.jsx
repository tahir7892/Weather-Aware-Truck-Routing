import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'

import ErrorMessage from './components/common/ErrorMessage'
import Loader from './components/common/Loader'
import ShortcutsHelp from './components/common/ShortcutsHelp'
import Warnings from './components/common/Warnings'
import ForecastSlider from './components/Heatmap/ForecastSlider'
import CheckpointTable from './components/Routes/CheckpointTable'
import RecommendationBanner from './components/Routes/RecommendationBanner'
import RouteList from './components/Routes/RouteList'
import RouteProfile from './components/Routes/RouteProfile'
import TripForm from './components/TripForm/TripForm'
import { useHeatmap } from './hooks/useHeatmap'
import { useTripPlanner } from './hooks/useTripPlanner'
import { defaultDepartureValue, localInputToIso, timeZoneName } from './utils/format'
import './App.css'

// The map library is large, so it loads in its own file while the form is already usable.
const TripMap = lazy(() => import('./components/Map/TripMap'))

const MAX_HOUR = 48

const TRUCK_ICON = (
  <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
    <path
      fill="currentColor"
      d="M3 6h11v9H3zM14 9h4l3 3v3h-7zM6.5 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zm11 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z"
    />
  </svg>
)

// One-click example trips (coordinates included, so no place lookup is needed).
const EXAMPLES = [
  {
    label: 'Chicago → Indianapolis',
    note: 'short · ~185 mi',
    origin: { name: 'Chicago, IL, USA', lat: 41.87897, lon: -87.66063 },
    destination: { name: 'Indianapolis, IN, USA', lat: 39.76838, lon: -86.15804 },
  },
  {
    label: 'Atlanta → Nashville',
    note: 'medium · ~250 mi',
    origin: { name: 'Atlanta, GA, USA', lat: 33.749, lon: -84.388 },
    destination: { name: 'Nashville, TN, USA', lat: 36.1627, lon: -86.7816 },
  },
  {
    label: 'Dallas → Denver',
    note: 'long · ~790 mi',
    origin: { name: 'Dallas, TX, USA', lat: 32.7767, lon: -96.797 },
    destination: { name: 'Denver, CO, USA', lat: 39.7392, lon: -104.9903 },
  },
]

function EmptyState({ onExample }) {
  return (
    <section className="card empty-state">
      <h2>Find the safest way there</h2>
      <p>Enter a trip above, or try an example:</p>
      <div className="examples">
        {EXAMPLES.map((example) => (
          <button key={example.label} type="button" className="example" onClick={() => onExample(example)}>
            <b>{example.label}</b>
            <span>{example.note} · 45,000 lb</span>
          </button>
        ))}
      </div>
      <p className="empty-how">We will:</p>
      <ul>
        <li>find 3 truck routes,</li>
        <li>check the weather every 10, 25 or 50 miles, for the time the truck gets there,</li>
        <li>rate wind, rain and snow risk for your load, and</li>
        <li>recommend the safest route, then the fastest.</li>
      </ul>
    </section>
  )
}

/** True when a key press is meant for a text field or control, not for our shortcuts. */
function isTypingTarget(target) {
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable
}

export default function App() {
  const { trip, loading, error, plan, clearError } = useTripPlanner()
  const heatmap = useHeatmap(trip?.trip_id)
  const [selectedRouteId, setSelectedRouteId] = useState(null)
  const [hoveredRouteId, setHoveredRouteId] = useState(null)
  const [hoverPoint, setHoverPoint] = useState(null)
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [showHeatmap, setShowHeatmap] = useState(true)
  const [heatmapView, setHeatmapView] = useState('risk')
  const [focusCheckpoint, setFocusCheckpoint] = useState(null)
  const [lastPayload, setLastPayload] = useState(null)
  const [preset, setPreset] = useState(null)
  const [showHelp, setShowHelp] = useState(false)

  const handlePlan = useCallback(
    async (payload) => {
      setLastPayload(payload)
      setPlaying(false)
      const result = await plan(payload)
      if (result) {
        setSelectedRouteId(result.recommendation.route_id)
        setHoveredRouteId(null)
        setHoverPoint(null)
        setHour(0)
        setFocusCheckpoint(null)
      }
    },
    [plan],
  )

  /** Example trip: show it in the form (re-created with these values) and plan it. */
  function startExample(example) {
    const departure = defaultDepartureValue()
    const values = { ...example, departure, loadLb: 45000, interval: 25, key: `${example.label}-${Date.now()}` }
    setPreset(values)
    handlePlan({
      origin: example.origin,
      destination: example.destination,
      departure_time: localInputToIso(departure),
      load_weight_lb: values.loadLb,
      checkpoint_interval_miles: values.interval,
    })
  }

  /** Select a route and open one of its checkpoints on the map. */
  const showCheckpoint = useCallback((routeId, index) => {
    setSelectedRouteId(routeId)
    setFocusCheckpoint({ routeId, index })
  }, [])

  const rankedRoutes = useMemo(() => (trip ? [...trip.routes].sort((a, b) => a.rank - b.rank) : []), [trip])

  // Keyboard shortcuts (ignored while typing in a field).
  useEffect(() => {
    function onKey(event) {
      if (event.ctrlKey || event.metaKey || event.altKey || isTypingTarget(event.target)) return
      if (event.key === '?') {
        setShowHelp((open) => !open)
      } else if (event.key === 'Escape') {
        setShowHelp(false)
      } else if (!trip) {
        // The remaining shortcuts need a planned trip.
      } else if (event.key === ' ' && event.target.tagName !== 'BUTTON') {
        event.preventDefault()
        setPlaying((p) => !p)
      } else if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault()
        setPlaying(false)
        setHour((h) => Math.min(MAX_HOUR, Math.max(0, h + (event.key === 'ArrowRight' ? 1 : -1))))
      } else if (['1', '2', '3'].includes(event.key)) {
        const route = rankedRoutes[Number(event.key) - 1]
        if (route) setSelectedRouteId(route.id)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [trip, rankedRoutes])

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
        <ShortcutsHelp open={showHelp} onToggle={() => setShowHelp((open) => !open)} />
      </header>

      <div className="main">
        <aside className="sidebar">
          <TripForm
            key={preset?.key ?? 'form'}
            initial={preset}
            onSubmit={handlePlan}
            onEdit={error ? clearError : undefined}
            loading={loading}
            serverErrors={formErrors}
          />

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
                <RouteList
                  key={trip.trip_id}
                  routes={trip.routes}
                  departureTime={trip.departure_time}
                  hour={hour}
                  selectedRouteId={selectedRouteId}
                  hoveredRouteId={hoveredRouteId}
                  onSelect={setSelectedRouteId}
                  onHover={setHoveredRouteId}
                  onHoverPoint={setHoverPoint}
                  onShowCheckpoint={showCheckpoint}
                />
                {selectedRoute && (
                  <>
                    <RouteProfile
                      route={selectedRoute}
                      departureTime={trip.departure_time}
                      hour={hour}
                      onHoverPoint={setHoverPoint}
                      onShowCheckpoint={showCheckpoint}
                    />
                    <CheckpointTable
                      route={selectedRoute}
                      interval={trip.checkpoint_interval_miles}
                      onShowCheckpoint={(index) => showCheckpoint(selectedRoute.id, index)}
                      onHoverPoint={setHoverPoint}
                    />
                  </>
                )}
              </>
            ) : (
              !loading && <EmptyState onExample={startExample} />
            )}
          </div>
        </aside>

        <section className="map-wrap">
          <Suspense fallback={<div className="map-loading">Loading map…</div>}>
            <TripMap
              trip={trip}
              selectedRouteId={selectedRouteId}
              hoveredRouteId={hoveredRouteId}
              onSelectRoute={setSelectedRouteId}
              onHoverRoute={setHoveredRouteId}
              hour={hour}
              heatmap={heatmap.data}
              heatmapView={heatmapView}
              showHeatmap={showHeatmap}
              focusCheckpoint={focusCheckpoint}
              hoverPoint={hoverPoint}
            />
          </Suspense>
          <ForecastSlider
            hour={hour}
            onHourChange={setHour}
            playing={playing}
            onPlayingChange={setPlaying}
            departureTime={trip?.departure_time}
            heatmapStatus={heatmap.status}
            heatmap={heatmap.data}
            onRetry={heatmap.retry}
            showHeatmap={showHeatmap}
            onToggleHeatmap={setShowHeatmap}
            view={heatmapView}
            onViewChange={setHeatmapView}
          />
        </section>
      </div>
    </div>
  )
}

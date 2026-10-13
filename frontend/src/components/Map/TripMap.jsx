import { Map as MapLibreMap, NavigationControl, setWorkerUrl } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState } from 'react'

import { boundsOf } from '../../utils/geo'
import CheckpointLayer from './CheckpointLayer'
import HeatmapLayer from './HeatmapLayer'
import MapLegend from './MapLegend'
import RouteLayer from './RouteLayer'
import TruckMarker from './TruckMarker'
import './Map.css'

// MapLibre looks for its worker next to its own file, which Vite moves; point it at the real file.
setWorkerUrl(workerUrl)

// Free CARTO base map built on OpenStreetMap data; no API key needed.
const STYLE_URL = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'
const USA_VIEW = { center: [-96, 38.5], zoom: 3.4 }

function fitPadding(container) {
  if (container.clientWidth < 640) return { top: 30, bottom: 170, left: 30, right: 30 }
  return { top: 60, bottom: 180, left: 60, right: 200 }
}

/**
 * The map and everything drawn on it. Layers are only mounted once the base
 * map has loaded; they are added in render order (heatmap below routes below
 * checkpoints).
 */
export default function TripMap({ trip, selectedRouteId, onSelectRoute, hour, heatmap, showHeatmap, focusCheckpoint }) {
  const containerRef = useRef(null)
  const [map, setMap] = useState(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let loaded = false
    const instance = new MapLibreMap({
      container: containerRef.current,
      style: STYLE_URL,
      ...USA_VIEW,
      attributionControl: { compact: true },
    })
    instance.addControl(new NavigationControl({ showCompass: false }), 'top-left')
    instance.on('load', () => {
      loaded = true
      setMap(instance)
    })
    instance.on('error', () => {
      if (!loaded) setFailed(true)
    })
    return () => {
      setMap(null)
      instance.remove()
    }
  }, [])

  // Zoom to the routes whenever a new trip arrives.
  useEffect(() => {
    if (!map || !trip) return
    map.fitBounds(boundsOf(trip.routes.map((route) => route.geometry)), {
      padding: fitPadding(containerRef.current),
      duration: 700,
      maxZoom: 11,
    })
  }, [map, trip])

  const selectedRoute = trip?.routes.find((route) => route.id === selectedRouteId)

  return (
    <div className="trip-map">
      <div ref={containerRef} className="map-canvas" role="region" aria-label="Map of routes, checkpoints and weather" />

      {map && (
        <>
          <HeatmapLayer map={map} heatmap={heatmap} hour={hour} visible={showHeatmap} />
          {trip && (
            <>
              <RouteLayer map={map} trip={trip} selectedRouteId={selectedRouteId} onSelectRoute={onSelectRoute} />
              <CheckpointLayer map={map} trip={trip} selectedRouteId={selectedRouteId} focus={focusCheckpoint} />
              {selectedRoute && <TruckMarker map={map} route={selectedRoute} departureTime={trip.departure_time} hour={hour} />}
            </>
          )}
        </>
      )}

      <MapLegend />

      {!trip && !failed && (
        <div className="map-hint">Enter a trip on the left to see 3 routes, their checkpoints and the weather.</div>
      )}
      {failed && (
        <div className="map-hint is-error">The map could not load. Check your internet connection and reload the page.</div>
      )}
    </div>
  )
}

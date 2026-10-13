import { Marker } from 'maplibre-gl'
import { useEffect, useMemo, useRef } from 'react'

import { formatDuration, formatMiles, formatTime } from '../../utils/format'
import { haversineMiles, toLngLat } from '../../utils/geo'

const SOURCE = 'routes'
const CASING = 'routes-casing'
const LINE = 'routes-line'

function chip(text, className, title) {
  const el = document.createElement('div')
  el.className = `map-chip ${className}`
  el.textContent = text
  if (title) el.title = title
  return el
}

const every = (line, n) => line.filter((_, i) => i % n === 0)

/**
 * One label spot per route: the point (between 20% and 80% of the way) that
 * is farthest from the other routes and from labels already placed, so the
 * labels sit where the routes have split apart and don't cover each other.
 */
function labelPoints(routes) {
  const placed = []
  const spots = {}
  for (const route of routes) {
    const others = routes.filter((r) => r !== route).flatMap((r) => every(r.geometry, 3))
    const last = route.geometry.length - 1
    let best = route.geometry[Math.floor(last / 2)]
    let bestScore = -1
    for (let f = 0.2; f <= 0.8; f += 0.05) {
      const point = route.geometry[Math.floor(last * f)]
      const fromRoutes = others.length ? Math.min(...others.map((p) => haversineMiles(point, p))) : 0
      const fromLabels = placed.length ? Math.min(...placed.map((p) => haversineMiles(point, p))) : Infinity
      const score = Math.min(fromRoutes, fromLabels / 2)
      if (score > bestScore) {
        bestScore = score
        best = point
      }
    }
    placed.push(best)
    spots[route.id] = best
  }
  return spots
}

/**
 * Draws the 3 routes (selected one in blue on top, others gray), a label on
 * each route with its letter and drive time, and the start / end markers.
 */
export default function RouteLayer({ map, trip, selectedRouteId, onSelectRoute }) {
  const onSelectRef = useRef(onSelectRoute)
  useEffect(() => {
    onSelectRef.current = onSelectRoute
  }, [onSelectRoute])

  // Add the source and layers once.
  useEffect(() => {
    const styles = getComputedStyle(document.documentElement)
    const selected = ['case', ['get', 'selected'], 2, 1]
    map.addSource(SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addLayer({
      id: CASING,
      type: 'line',
      source: SOURCE,
      layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': selected },
      paint: { 'line-color': '#ffffff', 'line-width': ['case', ['get', 'selected'], 10, 7] },
    })
    map.addLayer({
      id: LINE,
      type: 'line',
      source: SOURCE,
      layout: { 'line-join': 'round', 'line-cap': 'round', 'line-sort-key': selected },
      paint: {
        'line-color': [
          'case',
          ['get', 'selected'],
          styles.getPropertyValue('--route-selected').trim(),
          styles.getPropertyValue('--route-other').trim(),
        ],
        'line-width': ['case', ['get', 'selected'], 6, 4],
      },
    })

    const handleClick = (event) => onSelectRef.current(event.features[0].properties.id)
    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const reset = () => (map.getCanvas().style.cursor = '')
    map.on('click', LINE, handleClick)
    map.on('mouseenter', LINE, pointer)
    map.on('mouseleave', LINE, reset)

    return () => {
      map.off('click', LINE, handleClick)
      map.off('mouseenter', LINE, pointer)
      map.off('mouseleave', LINE, reset)
      try {
        map.removeLayer(LINE)
        map.removeLayer(CASING)
        map.removeSource(SOURCE)
      } catch {
        // The map itself was already removed.
      }
    }
  }, [map])

  // Update the lines when the trip or the selected route changes.
  useEffect(() => {
    map.getSource(SOURCE)?.setData({
      type: 'FeatureCollection',
      features: trip.routes.map((route) => ({
        type: 'Feature',
        properties: { id: route.id, selected: route.id === selectedRouteId },
        geometry: { type: 'LineString', coordinates: route.geometry.map(toLngLat) },
      })),
    })
  }, [map, trip, selectedRouteId])

  const labelSpots = useMemo(() => labelPoints(trip.routes), [trip])

  // Route labels and start / end markers (HTML markers so they stay crisp).
  useEffect(() => {
    // Start / End float just above their point so the truck icon can sit on it.
    const endpoint = { anchor: 'bottom', offset: [0, -6] }
    const markers = [
      new Marker({ element: chip('Start', 'is-endpoint', trip.origin.name), ...endpoint }).setLngLat([trip.origin.lon, trip.origin.lat]),
      new Marker({ element: chip('End', 'is-endpoint', trip.destination.name), ...endpoint }).setLngLat([trip.destination.lon, trip.destination.lat]),
    ]
    for (const route of trip.routes) {
      const { summary } = route
      const label = chip(
        `${route.id} · ${formatDuration(summary.duration_minutes)}`,
        route.id === selectedRouteId ? 'is-selected' : '',
        `Route ${route.id}${route.via ? ` via ${route.via}` : ''}: ${formatMiles(summary.distance_miles)}, ` +
          `arrives ${formatTime(summary.arrival_time)}, worst risk ${summary.max_level ?? 'unknown'}`,
      )
      label.setAttribute('role', 'button')
      label.addEventListener('click', () => onSelectRef.current(route.id))
      markers.push(new Marker({ element: label }).setLngLat(toLngLat(labelSpots[route.id])))
    }
    markers.forEach((marker) => marker.addTo(map))
    return () => markers.forEach((marker) => marker.remove())
  }, [map, trip, selectedRouteId, labelSpots])

  return null
}

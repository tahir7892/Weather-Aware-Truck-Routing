import { Marker } from 'maplibre-gl'
import { useCallback, useEffect, useMemo, useRef } from 'react'

import { formatDuration, formatMiles, formatTime } from '../../utils/format'
import { haversineMiles, toLngLat } from '../../utils/geo'
import { prefersReducedMotion } from '../../utils/motion'

const SOURCE = 'routes'
const CASING = 'routes-casing'
const LINE = 'routes-line'
const DRAW_MS = 900

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
 * New routes "draw in"; hovering a route (here or on its card) fades the others.
 */
export default function RouteLayer({ map, trip, selectedRouteId, hoveredRouteId, onSelectRoute, onHoverRoute }) {
  const onSelectRef = useRef(onSelectRoute)
  const onHoverRef = useRef(onHoverRoute)
  const selectedRef = useRef(selectedRouteId)
  const progressRef = useRef(1)
  const labelsRef = useRef({})
  useEffect(() => {
    onSelectRef.current = onSelectRoute
    onHoverRef.current = onHoverRoute
    selectedRef.current = selectedRouteId
  })

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
      paint: {
        'line-color': '#ffffff',
        'line-width': ['case', ['get', 'selected'], 10, 7],
        'line-opacity-transition': { duration: 200 },
      },
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
        'line-opacity-transition': { duration: 200 },
      },
    })

    const handleClick = (event) => onSelectRef.current(event.features[0].properties.id)
    const handleMove = (event) => {
      map.getCanvas().style.cursor = 'pointer'
      onHoverRef.current?.(event.features[0].properties.id)
    }
    const handleLeave = () => {
      map.getCanvas().style.cursor = ''
      onHoverRef.current?.(null)
    }
    map.on('click', LINE, handleClick)
    map.on('mousemove', LINE, handleMove)
    map.on('mouseleave', LINE, handleLeave)

    return () => {
      map.off('click', LINE, handleClick)
      map.off('mousemove', LINE, handleMove)
      map.off('mouseleave', LINE, handleLeave)
      try {
        map.removeLayer(LINE)
        map.removeLayer(CASING)
        map.removeSource(SOURCE)
      } catch {
        // The map itself was already removed.
      }
    }
  }, [map])

  // Draw the lines, each cut to `progressRef` of its length (for the draw-in animation).
  const draw = useCallback(() => {
    const fraction = progressRef.current
    map.getSource(SOURCE)?.setData({
      type: 'FeatureCollection',
      features: trip.routes.map((route) => {
        const count = Math.max(2, Math.ceil(route.geometry.length * fraction))
        return {
          type: 'Feature',
          properties: { id: route.id, selected: route.id === selectedRef.current },
          geometry: { type: 'LineString', coordinates: route.geometry.slice(0, count).map(toLngLat) },
        }
      }),
    })
  }, [map, trip])

  // A new trip: animate the lines from start to end.
  useEffect(() => {
    if (prefersReducedMotion()) {
      progressRef.current = 1
      draw()
      return undefined
    }
    const start = performance.now()
    let frame
    const tick = (now) => {
      const t = Math.min(1, (now - start) / DRAW_MS)
      progressRef.current = 1 - (1 - t) ** 3
      draw()
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    progressRef.current = 0
    frame = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(frame)
      progressRef.current = 1
    }
  }, [draw])

  // Selection changed: redraw at the current animation progress.
  useEffect(() => {
    draw()
  }, [draw, selectedRouteId])

  // Hovered route (on the map or its card): fade the other routes.
  useEffect(() => {
    if (!map.getLayer(LINE)) return
    const opacity = hoveredRouteId ? ['case', ['==', ['get', 'id'], hoveredRouteId], 1, 0.25] : 1
    map.setPaintProperty(LINE, 'line-opacity', opacity)
    map.setPaintProperty(CASING, 'line-opacity', opacity)
  }, [map, hoveredRouteId])

  const labelSpots = useMemo(() => labelPoints(trip.routes), [trip])

  // Route labels and start / end markers, created once per trip (HTML markers stay crisp).
  useEffect(() => {
    // Start / End float just above their point so the truck icon can sit on it.
    const endpoint = { anchor: 'bottom', offset: [0, -6] }
    const markers = [
      new Marker({ element: chip('Start', 'is-endpoint', trip.origin.name), ...endpoint }).setLngLat([trip.origin.lon, trip.origin.lat]),
      new Marker({ element: chip('End', 'is-endpoint', trip.destination.name), ...endpoint }).setLngLat([trip.destination.lon, trip.destination.lat]),
    ]
    const labels = {}
    for (const route of trip.routes) {
      const { summary } = route
      const label = chip(
        `${route.id} · ${formatDuration(summary.duration_minutes)}`,
        'is-route',
        `Route ${route.id}${route.via ? ` via ${route.via}` : ''}: ${formatMiles(summary.distance_miles)}, ` +
          `arrives ${formatTime(summary.arrival_time)}, worst risk ${summary.max_level ?? 'unknown'}`,
      )
      label.setAttribute('role', 'button')
      label.addEventListener('click', () => onSelectRef.current(route.id))
      label.addEventListener('mouseenter', () => onHoverRef.current?.(route.id))
      label.addEventListener('mouseleave', () => onHoverRef.current?.(null))
      labels[route.id] = label
      markers.push(new Marker({ element: label }).setLngLat(toLngLat(labelSpots[route.id])))
    }
    labelsRef.current = labels
    markers.forEach((marker) => marker.addTo(map))
    return () => markers.forEach((marker) => marker.remove())
  }, [map, trip, labelSpots])

  // Highlight the selected route's label.
  useEffect(() => {
    for (const [id, label] of Object.entries(labelsRef.current)) {
      label.classList.toggle('is-selected', id === selectedRouteId)
    }
  }, [trip, selectedRouteId])

  return null
}

import { Popup } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

import { formatDayTime, formatNumber, formatTime } from '../../utils/format'
import { riskByLabel, riskColorExpression } from '../../utils/risk'

const SOURCE = 'checkpoints'
const LAYER = 'checkpoints'

function el(tag, className, text) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text !== undefined) node.textContent = text
  return node
}

/** Popup content built with DOM nodes (text only, never HTML from the API). */
function popupContent(route, checkpoint) {
  const risk = riskByLabel(checkpoint.risk.level)
  const { weather } = checkpoint
  const root = el('div', 'cp-pop')

  const head = el('div', 'cp-head')
  head.append(el('strong', '', `Route ${route.id} · mile ${formatNumber(checkpoint.mile)}`))
  const badge = el('span', 'risk-badge')
  const dot = el('span', 'risk-dot')
  dot.style.background = risk.color
  badge.append(dot, checkpoint.risk.level)
  head.append(badge)
  root.append(head)

  const rows = [
    ['Truck arrives', formatDayTime(checkpoint.eta)],
    ['Forecast hour used', formatTime(checkpoint.forecast_time)],
  ]
  for (const [label, value] of rows) {
    const row = el('div', 'cp-row')
    row.append(el('span', '', label), el('b', '', value))
    root.append(row)
  }

  const grid = el('div', 'cp-grid')
  const cells = [
    ['Wind', weather.wind_mph === null ? '—' : `${formatNumber(weather.wind_mph)} mph`],
    ['Gusts', weather.gust_mph === null ? '—' : `${formatNumber(weather.gust_mph)} mph`],
    ['Rain', weather.rain_in_per_hr === null ? '—' : `${formatNumber(weather.rain_in_per_hr, 2)} in/hr`],
    ['Snow', weather.snow_in_per_hr === null ? '—' : `${formatNumber(weather.snow_in_per_hr, 2)} in/hr`],
  ]
  for (const [label, value] of cells) {
    const cell = el('div')
    cell.append(el('span', '', label), el('b', '', value))
    grid.append(cell)
  }
  root.append(grid, el('p', 'cp-reason', checkpoint.risk.reason))
  return root
}

/**
 * Checkpoint dots colored by risk (bigger on the selected route). Clicking a
 * dot, or a row in the checkpoint table (`focus`), opens its details.
 */
export default function CheckpointLayer({ map, trip, selectedRouteId, focus }) {
  const popupRef = useRef(null)
  const tripRef = useRef(trip)
  useEffect(() => {
    tripRef.current = trip
  }, [trip])

  function openPopup(routeId, index, { fly = false } = {}) {
    const route = tripRef.current.routes.find((r) => r.id === routeId)
    const checkpoint = route?.checkpoints[index]
    if (!checkpoint) return
    popupRef.current?.remove()
    popupRef.current = new Popup({ maxWidth: '280px', className: 'cp-popup', focusAfterOpen: false })
      .setLngLat([checkpoint.lon, checkpoint.lat])
      .setDOMContent(popupContent(route, checkpoint))
      .addTo(map)
    if (fly) map.easeTo({ center: [checkpoint.lon, checkpoint.lat], zoom: Math.max(map.getZoom(), 8), duration: 600 })
  }
  const openRef = useRef(openPopup)
  useEffect(() => {
    openRef.current = openPopup
  })

  useEffect(() => {
    map.addSource(SOURCE, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    map.addLayer({
      id: LAYER,
      type: 'circle',
      source: SOURCE,
      layout: { 'circle-sort-key': ['case', ['get', 'selected'], 2, 1] },
      paint: {
        'circle-color': riskColorExpression(),
        'circle-radius': ['case', ['get', 'selected'], 7, 4.5],
        'circle-opacity': ['case', ['get', 'selected'], 1, 0.75],
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 2,
      },
    })

    const handleClick = (event) => {
      const { route, index } = event.features[0].properties
      openRef.current(route, index)
    }
    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const reset = () => (map.getCanvas().style.cursor = '')
    map.on('click', LAYER, handleClick)
    map.on('mouseenter', LAYER, pointer)
    map.on('mouseleave', LAYER, reset)

    return () => {
      map.off('click', LAYER, handleClick)
      map.off('mouseenter', LAYER, pointer)
      map.off('mouseleave', LAYER, reset)
      popupRef.current?.remove()
      try {
        map.removeLayer(LAYER)
        map.removeSource(SOURCE)
      } catch {
        // The map itself was already removed.
      }
    }
  }, [map])

  useEffect(() => {
    map.getSource(SOURCE)?.setData({
      type: 'FeatureCollection',
      features: trip.routes.flatMap((route) =>
        route.checkpoints.map((checkpoint) => ({
          type: 'Feature',
          properties: {
            route: route.id,
            index: checkpoint.index,
            risk: checkpoint.risk.score ?? -1,
            selected: route.id === selectedRouteId,
          },
          geometry: { type: 'Point', coordinates: [checkpoint.lon, checkpoint.lat] },
        })),
      ),
    })
  }, [map, trip, selectedRouteId])

  // A new trip closes any open popup.
  useEffect(() => () => popupRef.current?.remove(), [trip])

  // Row clicked in the checkpoint table.
  useEffect(() => {
    if (focus) openRef.current(focus.routeId, focus.index, { fly: true })
  }, [focus])

  return null
}

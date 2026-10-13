import { Marker } from 'maplibre-gl'
import { useEffect, useMemo, useRef } from 'react'

import { formatDayTime } from '../../utils/format'
import { cumulativeMiles, toLngLat, truckPosition } from '../../utils/geo'

const TRUCK_SVG =
  '<svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path fill="currentColor" d="M3 6h11v9H3zM14 9h4l3 3v3h-7zM6.5 18.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zm11 0a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z"/></svg>'

/** Where the truck on the selected route will be at the slider's hour. */
export default function TruckMarker({ map, route, departureTime, hour }) {
  const markerRef = useRef(null)
  const cumulative = useMemo(() => cumulativeMiles(route.geometry), [route])

  useEffect(() => {
    const element = document.createElement('div')
    element.className = 'truck-marker'
    element.innerHTML = TRUCK_SVG
    markerRef.current = new Marker({ element }).setLngLat([0, 0])
    return () => markerRef.current.remove()
  }, [])

  useEffect(() => {
    const moment = new Date(new Date(departureTime).getTime() + hour * 3600e3)
    const position = truckPosition(route, moment, cumulative)
    const marker = markerRef.current
    marker.setLngLat(toLngLat(position.point)).addTo(map)

    const element = marker.getElement()
    element.classList.toggle('is-arrived', position.arrived)
    element.title = position.arrived
      ? `Route ${route.id}: arrived by ${formatDayTime(moment)}`
      : `Route ${route.id}: where the truck will be at ${formatDayTime(moment)}`
  }, [map, route, departureTime, hour, cumulative])

  return null
}

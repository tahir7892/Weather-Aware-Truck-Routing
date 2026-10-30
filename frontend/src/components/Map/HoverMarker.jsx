import { Marker } from 'maplibre-gl'
import { useEffect, useRef } from 'react'

/**
 * A pulsing ring on the map at `point` ({ lat, lon }): shows where the
 * checkpoint, ribbon piece or chart point under the mouse is.
 */
export default function HoverMarker({ map, point }) {
  const markerRef = useRef(null)

  useEffect(() => {
    const element = document.createElement('div')
    element.className = 'hover-marker'
    markerRef.current = new Marker({ element })
    return () => markerRef.current.remove()
  }, [])

  useEffect(() => {
    const marker = markerRef.current
    if (point) marker.setLngLat([point.lon, point.lat]).addTo(map)
    else marker.remove()
  }, [map, point])

  return null
}

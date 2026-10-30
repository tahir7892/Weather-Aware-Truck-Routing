import { useEffect, useRef } from 'react'

import { HEATMAP_VIEWS, heatColorExpression } from '../../utils/risk'
import { prefersReducedMotion } from '../../utils/motion'

const EMPTY = { type: 'FeatureCollection', features: [] }
const OPACITY = 0.45
const FADE_MS = 280
// Two copies of the layer: the new hour fades in on one while the old hour fades out on the other.
const LAYERS = [
  { source: 'heatmap-a', layer: 'heatmap-a-fill' },
  { source: 'heatmap-b', layer: 'heatmap-b-fill' },
]

/**
 * Weather squares along the trip corridor for the selected hour, showing
 * overall risk or one condition (wind, rain, snow). All 49 hours are prepared
 * in advance; changing the hour swaps the data and cross-fades the two layers.
 */
export default function HeatmapLayer({ map, heatmap, hour, visible, view }) {
  const activeRef = useRef(0)

  useEffect(() => {
    const fade = { duration: prefersReducedMotion() ? 0 : FADE_MS, delay: 0 }
    for (const { source, layer } of LAYERS) {
      map.addSource(source, { type: 'geojson', data: EMPTY })
      map.addLayer({
        id: layer,
        type: 'fill',
        source,
        paint: {
          'fill-color': heatColorExpression('risk'),
          'fill-opacity': 0,
          'fill-opacity-transition': fade,
          'fill-antialias': false,
        },
      })
    }
    return () => {
      try {
        for (const { source, layer } of LAYERS) {
          map.removeLayer(layer)
          map.removeSource(source)
        }
      } catch {
        // The map itself was already removed.
      }
    }
  }, [map])

  // New hour (or new trip): put it on the hidden copy, fade that in and the other out.
  useEffect(() => {
    const frame = heatmap?.frames[Math.min(hour, heatmap.frames.length - 1)]
    const next = 1 - activeRef.current
    map.getSource(LAYERS[next].source)?.setData(frame ?? EMPTY)
    if (!map.getLayer(LAYERS[next].layer)) return
    map.setPaintProperty(LAYERS[next].layer, 'fill-opacity', frame ? OPACITY : 0)
    map.setPaintProperty(LAYERS[activeRef.current].layer, 'fill-opacity', 0)
    activeRef.current = next
  }, [map, heatmap, hour])

  // Risk / wind / rain / snow.
  useEffect(() => {
    const property = (HEATMAP_VIEWS.find((v) => v.id === view) ?? HEATMAP_VIEWS[0]).property
    for (const { layer } of LAYERS) {
      if (map.getLayer(layer)) map.setPaintProperty(layer, 'fill-color', heatColorExpression(property))
    }
  }, [map, view])

  useEffect(() => {
    for (const { layer } of LAYERS) {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', visible ? 'visible' : 'none')
    }
  }, [map, visible])

  return null
}

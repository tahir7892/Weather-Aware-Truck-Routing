import { useEffect } from 'react'

import { riskColorExpression } from '../../utils/risk'

const SOURCE = 'heatmap'
const LAYER = 'heatmap-fill'
const EMPTY = { type: 'FeatureCollection', features: [] }

/**
 * Weather risk squares along the trip corridor for the selected hour. All 49
 * hours are prepared in advance, so changing the hour only swaps the data.
 */
export default function HeatmapLayer({ map, heatmap, hour, visible }) {
  useEffect(() => {
    map.addSource(SOURCE, { type: 'geojson', data: EMPTY })
    map.addLayer({
      id: LAYER,
      type: 'fill',
      source: SOURCE,
      paint: {
        'fill-color': riskColorExpression(),
        // Low is a faint tint, risky cells stand out, "no data" stays empty.
        'fill-opacity': ['match', ['get', 'risk'], -1, 0, 0, 0.07, 0.42],
        'fill-antialias': false,
      },
    })
    return () => {
      try {
        map.removeLayer(LAYER)
        map.removeSource(SOURCE)
      } catch {
        // The map itself was already removed.
      }
    }
  }, [map])

  useEffect(() => {
    const frame = heatmap?.frames[Math.min(hour, heatmap.frames.length - 1)]
    map.getSource(SOURCE)?.setData(frame ?? EMPTY)
  }, [map, heatmap, hour])

  useEffect(() => {
    if (map.getLayer(LAYER)) map.setLayoutProperty(LAYER, 'visibility', visible ? 'visible' : 'none')
  }, [map, visible])

  return null
}

/*
 * Turns the backend's heatmap response into 49 ready-to-draw map layers, once.
 * Moving the slider then only swaps which prepared layer is shown, so it stays
 * smooth: no network calls and no recalculation while sliding.
 */

import { conditionLevel } from './risk'

const MILES_PER_DEGREE_LAT = 69.09

export function prepareHeatmap(data) {
  const halfLat = data.grid_spacing_miles / MILES_PER_DEGREE_LAT / 2

  // One square cell per grid point, shared by every hour.
  const geometries = data.points.map(([lat, lon]) => {
    const halfLon = data.grid_spacing_miles / (MILES_PER_DEGREE_LAT * Math.cos((lat * Math.PI) / 180)) / 2
    return {
      type: 'Polygon',
      coordinates: [
        [
          [lon - halfLon, lat - halfLat],
          [lon + halfLon, lat - halfLat],
          [lon + halfLon, lat + halfLat],
          [lon - halfLon, lat + halfLat],
          [lon - halfLon, lat - halfLat],
        ],
      ],
    }
  })

  // Every cell carries a 0-4 level for each view (risk, wind, rain, snow);
  // -1 marks "no data" so the map leaves that cell empty.
  const frames = data.frames.map((frame) => ({
    type: 'FeatureCollection',
    features: geometries.map((geometry, i) => ({
      type: 'Feature',
      geometry,
      properties: {
        risk: frame.risk[i] ?? -1,
        windLevel: conditionLevel('wind', frame.wind_mph[i]),
        rainLevel: conditionLevel('rain', frame.rain_in_per_hr[i]),
        snowLevel: conditionLevel('snow', frame.snow_in_per_hr[i]),
      },
    })),
  }))

  return {
    startTime: data.start_time,
    times: data.times,
    hours: data.hours,
    spacingMiles: data.grid_spacing_miles,
    corridorMiles: data.corridor_miles,
    pointCount: data.points.length,
    frames,
  }
}

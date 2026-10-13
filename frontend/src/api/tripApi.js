import { request } from './client'

/** GET /api/geocode/?q= -> [{ name, lat, lon }] */
export async function searchPlaces(query, signal) {
  const data = await request('/geocode/', { params: { q: query }, signal, timeoutMs: 15000 })
  return data.results
}

/**
 * POST /api/plan-trip/ -> trip with 3 routes, checkpoints and a recommendation.
 * `origin` / `destination` are text or { lat, lon, name }. A new trip calls
 * several outside services, which are occasionally very slow, so the wait is
 * generous (usually it takes a few seconds).
 */
export function planTrip(payload, signal) {
  return request('/plan-trip/', { method: 'POST', body: payload, signal, timeoutMs: 180000 })
}

/** GET /api/heatmap/?trip_id= -> grid points and 49 hourly risk frames. */
export function getHeatmap(tripId, signal) {
  return request('/heatmap/', { params: { trip_id: tripId }, signal, timeoutMs: 150000 })
}

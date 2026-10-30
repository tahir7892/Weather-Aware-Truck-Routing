/*
 * Small map helpers. Points from the backend are [lat, lon]; MapLibre wants
 * [lon, lat], so conversions happen here.
 */

const EARTH_RADIUS_MILES = 3958.8
const toRad = (degrees) => (degrees * Math.PI) / 180

export function haversineMiles([lat1, lon1], [lat2, lon2]) {
  const h =
    Math.sin(toRad(lat2 - lat1) / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(toRad(lon2 - lon1) / 2) ** 2
  return 2 * EARTH_RADIUS_MILES * Math.asin(Math.sqrt(Math.min(1, h)))
}

export const toLngLat = ([lat, lon]) => [lon, lat]

/** Miles from the start to each point of a [lat, lon] line. */
export function cumulativeMiles(line) {
  const out = [0]
  for (let i = 1; i < line.length; i += 1) out.push(out[i - 1] + haversineMiles(line[i - 1], line[i]))
  return out
}

/** The [lat, lon] point `mile` miles along a line (clamped to its ends). */
export function pointAtMile(line, cumulative, mile) {
  if (mile <= 0) return line[0]
  const last = line.length - 1
  if (mile >= cumulative[last]) return line[last]
  let i = 1
  while (cumulative[i] < mile) i += 1
  const span = cumulative[i] - cumulative[i - 1] || 1
  const t = (mile - cumulative[i - 1]) / span
  return [line[i - 1][0] + (line[i][0] - line[i - 1][0]) * t, line[i - 1][1] + (line[i][1] - line[i - 1][1]) * t]
}

/**
 * How far along `route` the truck is at `moment` (a Date), using the
 * checkpoints' mile markers and ETAs. Returns { mile, started, arrived }.
 */
export function mileAtTime(route, moment) {
  const checkpoints = route.checkpoints
  const time = moment.getTime()
  const first = Date.parse(checkpoints[0].eta)
  const lastCheckpoint = checkpoints[checkpoints.length - 1]
  const last = Date.parse(lastCheckpoint.eta)

  if (time <= first) return { mile: 0, started: false, arrived: false }
  if (time >= last) return { mile: lastCheckpoint.mile, started: true, arrived: true }

  let i = 1
  while (Date.parse(checkpoints[i].eta) < time) i += 1
  const a = checkpoints[i - 1]
  const b = checkpoints[i]
  const ta = Date.parse(a.eta)
  const tb = Date.parse(b.eta)
  return { mile: a.mile + ((b.mile - a.mile) * (time - ta)) / (tb - ta || 1), started: true, arrived: false }
}

/** Where a truck on `route` is at `moment`. Returns { point: [lat, lon], started, arrived }. */
export function truckPosition(route, moment, cumulative) {
  const { mile, started, arrived } = mileAtTime(route, moment)
  // Checkpoint miles follow the full road line; the drawn line is simplified, so scale.
  const lastMile = route.checkpoints[route.checkpoints.length - 1].mile || 1
  const scale = cumulative[cumulative.length - 1] / lastMile
  return { point: pointAtMile(route.geometry, cumulative, mile * scale), started, arrived }
}

/** Moment `hour` hours after an ISO departure time. */
export function momentAtHour(departureTime, hour) {
  return new Date(Date.parse(departureTime) + hour * 3600e3)
}

/** [[west, south], [east, north]] around every point of every line. */
export function boundsOf(lines) {
  let west = Infinity
  let south = Infinity
  let east = -Infinity
  let north = -Infinity
  for (const line of lines) {
    for (const [lat, lon] of line) {
      west = Math.min(west, lon)
      east = Math.max(east, lon)
      south = Math.min(south, lat)
      north = Math.max(north, lat)
    }
  }
  return [
    [west, south],
    [east, north],
  ]
}

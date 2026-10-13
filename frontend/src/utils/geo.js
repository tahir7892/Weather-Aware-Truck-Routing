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
 * Where a truck on `route` is at `moment` (a Date), using the checkpoints'
 * mile markers and ETAs. Returns { point: [lat, lon], arrived, started }.
 */
export function truckPosition(route, moment, cumulative) {
  const checkpoints = route.checkpoints
  const time = moment.getTime()
  const first = new Date(checkpoints[0].eta).getTime()
  const lastCheckpoint = checkpoints[checkpoints.length - 1]
  const last = new Date(lastCheckpoint.eta).getTime()

  let mile
  if (time <= first) mile = 0
  else if (time >= last) mile = lastCheckpoint.mile
  else {
    let i = 1
    while (new Date(checkpoints[i].eta).getTime() < time) i += 1
    const a = checkpoints[i - 1]
    const b = checkpoints[i]
    const ta = new Date(a.eta).getTime()
    const tb = new Date(b.eta).getTime()
    mile = a.mile + ((b.mile - a.mile) * (time - ta)) / (tb - ta || 1)
  }

  // Checkpoint miles follow the full road line; the drawn line is simplified, so scale.
  const scale = cumulative[cumulative.length - 1] / (lastCheckpoint.mile || 1)
  return {
    point: pointAtMile(route.geometry, cumulative, mile * scale),
    started: time > first,
    arrived: time >= last,
  }
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

/*
 * Formatting helpers. The backend sends times in UTC (ISO 8601); everything
 * shown to the user is converted to the browser's own time zone here.
 */

const timeFormat = new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' })
const dayTimeFormat = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' })

export function formatTime(value) {
  return timeFormat.format(new Date(value))
}

export function formatDayTime(value) {
  return dayTimeFormat.format(new Date(value))
}

/** e.g. "CDT" or "GMT+5:30" - the short name of the user's time zone. */
export function timeZoneName() {
  const parts = new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' }).formatToParts(new Date())
  return parts.find((part) => part.type === 'timeZoneName')?.value ?? 'local time'
}

export function formatDuration(minutes) {
  const total = Math.round(minutes)
  const hours = Math.floor(total / 60)
  const rest = total % 60
  return hours ? `${hours} h ${String(rest).padStart(2, '0')} min` : `${rest} min`
}

export function formatMiles(miles, digits = 1) {
  return `${Number(miles).toFixed(digits)} mi`
}

export function formatNumber(value, digits = 0) {
  return value === null || value === undefined ? '—' : Number(value).toFixed(digits)
}

/** A Date as the "YYYY-MM-DDTHH:mm" string a datetime-local input expects (local time). */
export function toLocalInputValue(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** The next whole hour from now, as a datetime-local value. */
export function defaultDepartureValue() {
  const next = new Date()
  next.setMinutes(0, 0, 0)
  next.setHours(next.getHours() + 1)
  return toLocalInputValue(next)
}

/** A datetime-local value (the user's local time) as a UTC ISO string for the API. */
export function localInputToIso(value) {
  return new Date(value).toISOString()
}

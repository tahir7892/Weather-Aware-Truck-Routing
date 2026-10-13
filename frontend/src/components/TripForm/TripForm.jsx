import { useState } from 'react'

import { defaultDepartureValue, localInputToIso, toLocalInputValue } from '../../utils/format'
import PlaceInput from './PlaceInput'
import './TripForm.css'

const INTERVALS = [10, 25, 50]
const MIN_LOAD = 1
const MAX_LOAD = 150000
const MAX_DAYS_AHEAD = 7
const PAST_TOLERANCE_MINUTES = 30

const emptyPlace = (text = '') => ({ text, place: null })

function placePayload({ text, place }) {
  return place ? { lat: place.lat, lon: place.lon, name: place.name } : text.trim()
}

/** Checks the form before sending, with the same limits as the backend. */
function validate({ origin, destination, departure, load }) {
  const errors = {}
  if (origin.text.trim().length < 2) errors.origin = 'Enter where the truck starts.'
  if (destination.text.trim().length < 2) errors.destination = 'Enter where the truck is going.'
  if (!errors.origin && !errors.destination && origin.text.trim().toLowerCase() === destination.text.trim().toLowerCase()) {
    errors.destination = 'Destination must be different from the origin.'
  }

  const when = new Date(departure)
  const now = Date.now()
  if (!departure || Number.isNaN(when.getTime())) errors.departure_time = 'Choose a departure date and time.'
  else if (when.getTime() < now - PAST_TOLERANCE_MINUTES * 60e3) errors.departure_time = 'Departure time is in the past.'
  else if (when.getTime() > now + MAX_DAYS_AHEAD * 864e5) errors.departure_time = `Departure must be within ${MAX_DAYS_AHEAD} days (forecast range).`

  const weight = Number(load)
  if (load === '' || !Number.isFinite(weight)) errors.load_weight_lb = 'Enter the load weight in pounds.'
  else if (weight < MIN_LOAD || weight > MAX_LOAD) errors.load_weight_lb = `Load must be between ${MIN_LOAD} and ${MAX_LOAD.toLocaleString()} lb.`

  return errors
}

/**
 * The "Plan a trip" card. Sends { origin, destination, departure_time,
 * load_weight_lb, checkpoint_interval_miles } to `onSubmit`.
 * `serverErrors` are field errors returned by the backend.
 */
export default function TripForm({ onSubmit, onEdit, loading, serverErrors }) {
  const [origin, setOrigin] = useState(emptyPlace())
  const [destination, setDestination] = useState(emptyPlace())
  const [departure, setDeparture] = useState(defaultDepartureValue)
  const [load, setLoad] = useState('45000')
  const [interval, setIntervalMiles] = useState(25)
  const [errors, setErrors] = useState({})
  // Date-picker limits, set when the form opens; submitting re-checks against the current time.
  const [{ minDeparture, maxDeparture }] = useState(() => {
    const now = new Date()
    return {
      minDeparture: toLocalInputValue(now),
      maxDeparture: toLocalInputValue(new Date(now.getTime() + MAX_DAYS_AHEAD * 864e5)),
    }
  })

  const fieldError = (name) => errors[name] || serverErrors?.[name]?.[0]

  function edited(name, setter) {
    return (value) => {
      setter(value)
      if (errors[name]) setErrors((current) => ({ ...current, [name]: undefined }))
      onEdit?.()
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    const found = validate({ origin, destination, departure, load })
    setErrors(found)
    if (Object.keys(found).length) return
    onSubmit({
      origin: placePayload(origin),
      destination: placePayload(destination),
      departure_time: localInputToIso(departure),
      load_weight_lb: Number(load),
      checkpoint_interval_miles: interval,
    })
  }

  function swap() {
    setOrigin(destination)
    setDestination(origin)
    onEdit?.()
  }

  return (
    <form className="card trip-form" onSubmit={handleSubmit} noValidate>
      <h2 className="card-title">Plan a trip</h2>

      <div className="places">
        <div className="places-stack">
          <PlaceInput
            id="origin"
            label="Origin"
            placeholder="City or address, e.g. Chicago, IL"
            value={origin}
            onChange={edited('origin', setOrigin)}
            error={fieldError('origin')}
          />
          <PlaceInput
            id="destination"
            label="Destination"
            placeholder="City or address, e.g. Indianapolis, IN"
            value={destination}
            onChange={edited('destination', setDestination)}
            error={fieldError('destination')}
          />
        </div>
        <button type="button" className="swap" onClick={swap} aria-label="Swap origin and destination" title="Swap origin and destination">
          ⇅
        </button>
      </div>

      <div className="row2">
        <div className="field">
          <label htmlFor="departure">Departure (your time)</label>
          <input
            id="departure"
            type="datetime-local"
            className={`input ${fieldError('departure_time') ? 'has-error' : ''}`}
            value={departure}
            min={minDeparture}
            max={maxDeparture}
            onChange={(event) => edited('departure_time', setDeparture)(event.target.value)}
            aria-invalid={Boolean(fieldError('departure_time'))}
          />
          {fieldError('departure_time') && <span className="field-error">{fieldError('departure_time')}</span>}
        </div>

        <div className="field">
          <label htmlFor="load">Load weight</label>
          <div className="suffix">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              className={`input ${fieldError('load_weight_lb') ? 'has-error' : ''}`}
              min={MIN_LOAD}
              max={MAX_LOAD}
              step="500"
              value={load}
              onChange={(event) => edited('load_weight_lb', setLoad)(event.target.value)}
              aria-invalid={Boolean(fieldError('load_weight_lb'))}
              aria-describedby="load-hint"
            />
            <span aria-hidden="true">lb</span>
          </div>
          {fieldError('load_weight_lb') && <span className="field-error">{fieldError('load_weight_lb')}</span>}
        </div>
      </div>
      <p id="load-hint" className="hint">
        Loads over 30,000 lb and 40,000 lb raise the risk from strong wind.
      </p>

      <div className="field">
        <span className="field-label" id="interval-label">
          Weather checkpoint every
        </span>
        <div className="segmented" role="group" aria-labelledby="interval-label">
          {INTERVALS.map((miles) => (
            <button
              key={miles}
              type="button"
              aria-pressed={interval === miles}
              onClick={() => {
                setIntervalMiles(miles)
                onEdit?.()
              }}
            >
              {miles} mi
            </button>
          ))}
        </div>
      </div>

      <button className="primary" type="submit" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner small" aria-hidden="true" /> Planning…
          </>
        ) : (
          'Plan safest route'
        )}
      </button>
    </form>
  )
}

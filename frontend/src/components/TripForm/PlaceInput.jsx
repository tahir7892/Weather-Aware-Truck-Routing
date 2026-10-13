import { useEffect, useId, useState } from 'react'

import { searchPlaces } from '../../api/tripApi'
import { useDebounce } from '../../hooks/useDebounce'

const MIN_QUERY_LENGTH = 3

/**
 * Text input with place suggestions from the backend (/api/geocode/).
 * `value` is { text, place }: `place` ({ name, lat, lon }) is set once the user
 * picks a suggestion, and cleared as soon as they type again.
 */
export default function PlaceInput({ id, label, value, onChange, error, placeholder }) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const [search, setSearch] = useState({ query: '', results: [], failed: false })
  const query = useDebounce(value.text.trim(), 300)

  const shouldSearch = open && !value.place && query.length >= MIN_QUERY_LENGTH

  useEffect(() => {
    if (!shouldSearch) return undefined
    const controller = new AbortController()
    searchPlaces(query, controller.signal)
      .then((results) => setSearch({ query, results, failed: false }))
      .catch((err) => {
        if (err.name !== 'AbortError') setSearch({ query, results: [], failed: true })
      })
    return () => controller.abort()
  }, [query, shouldSearch])

  const searchDone = search.query === query
  const results = shouldSearch && searchDone ? search.results : []
  const searching = shouldSearch && !searchDone
  const showList = shouldSearch

  function pick(place) {
    onChange({ text: place.name, place })
    setOpen(false)
    setActiveIndex(-1)
  }

  function handleKeyDown(event) {
    if (!showList || !results.length) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActiveIndex((i) => (i + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActiveIndex((i) => (i <= 0 ? results.length - 1 : i - 1))
    } else if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault()
      pick(results[activeIndex])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const errorId = `${id}-error`

  return (
    <div className={`field place-field ${value.place ? 'is-confirmed' : ''}`}>
      <label htmlFor={id}>{label}</label>
      <div className="place-input-wrap">
        <svg className="place-pin" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <path fill="currentColor" d="M12 2a7 7 0 0 0-7 7c0 5 7 13 7 13s7-8 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z" />
        </svg>
        <input
          id={id}
          className={`input with-icon ${error ? 'has-error' : ''}`}
          value={value.text}
          placeholder={placeholder}
          autoComplete="off"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeIndex >= 0 ? `${listId}-${activeIndex}` : undefined}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          onChange={(event) => {
            onChange({ text: event.target.value, place: null })
            setOpen(true)
            setActiveIndex(-1)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onKeyDown={handleKeyDown}
        />
      </div>

      {showList && (
        <ul id={listId} className="suggest" role="listbox">
          {searching && <li className="suggest-note">Searching…</li>}
          {!searching && search.failed && <li className="suggest-note">Suggestions are unavailable right now. You can still type the full place name.</li>}
          {!searching && !search.failed && !results.length && <li className="suggest-note">No matching places. Try a city and state, e.g. “Dallas, TX”.</li>}
          {results.map((place, index) => (
            <li
              key={`${place.name}-${place.lat}-${place.lon}`}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === activeIndex}
              className={index === activeIndex ? 'is-active' : ''}
              onMouseDown={(event) => {
                event.preventDefault()
                pick(place)
              }}
            >
              <span className="suggest-pin" aria-hidden="true">●</span>
              {place.name}
            </li>
          ))}
        </ul>
      )}

      {error && (
        <span id={errorId} className="field-error">
          {error}
        </span>
      )}
    </div>
  )
}

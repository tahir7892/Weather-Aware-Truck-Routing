import { NO_DATA, RISK_LEVELS } from '../../utils/risk'

/** Color key for risk levels and route lines. */
export default function MapLegend() {
  return (
    <aside className="legend" aria-label="Map legend">
      <h3>Weather risk</h3>
      <ul>
        {[...RISK_LEVELS, NO_DATA].map((level) => (
          <li key={level.label}>
            <span className="swatch" style={{ background: level.color }} />
            {level.label}
          </li>
        ))}
      </ul>
      <div className="legend-lines">
        <div>
          <span className="line-swatch is-selected" />
          Selected route
        </div>
        <div>
          <span className="line-swatch" />
          Other routes
        </div>
      </div>
    </aside>
  )
}

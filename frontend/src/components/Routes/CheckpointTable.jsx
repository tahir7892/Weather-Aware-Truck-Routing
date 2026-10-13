import { formatNumber, formatTime } from '../../utils/format'
import { riskByLabel } from '../../utils/risk'
import './Routes.css'

/** Every checkpoint of the selected route. Clicking a row shows it on the map. */
export default function CheckpointTable({ route, interval, onShowCheckpoint }) {
  return (
    <section className="card table-card">
      <h2 className="card-title">
        Checkpoints · Route {route.id}
        <span className="table-sub">every {interval} mi · click a row to see it on the map</span>
      </h2>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th scope="col">Mile</th>
              <th scope="col">Arrives</th>
              <th scope="col">Wind</th>
              <th scope="col">Rain</th>
              <th scope="col">Snow</th>
              <th scope="col">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((checkpoint) => {
              const risk = riskByLabel(checkpoint.risk.level)
              const { weather } = checkpoint
              return (
                <tr key={checkpoint.index} onClick={() => onShowCheckpoint(checkpoint.index)} title={checkpoint.risk.reason}>
                  <td>
                    <button type="button" className="row-link" onClick={(event) => {
                      event.stopPropagation()
                      onShowCheckpoint(checkpoint.index)
                    }}>
                      {formatNumber(checkpoint.mile)}
                    </button>
                  </td>
                  <td>{formatTime(checkpoint.eta)}</td>
                  <td>{weather.wind_mph === null ? '—' : `${formatNumber(weather.wind_mph)} mph`}</td>
                  <td>{formatNumber(weather.rain_in_per_hr, 2)}</td>
                  <td>{formatNumber(weather.snow_in_per_hr, 2)}</td>
                  <td>
                    <span className="risk-badge">
                      <span className="risk-dot" style={{ background: risk.color }} />
                      {checkpoint.risk.level}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <p className="table-note">Rain and snow in inches per hour. Times are in your local time.</p>
    </section>
  )
}

import './common.css'

/** Yellow boxes for the backend's trip warnings. */
export default function Warnings({ warnings }) {
  if (!warnings?.length) return null

  return (
    <div className="warnings">
      {warnings.map((warning) => (
        <div key={warning} className="warning" role="note">
          <span aria-hidden="true">!</span>
          {warning}
        </div>
      ))}
    </div>
  )
}

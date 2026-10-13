import './common.css'

const TITLES = {
  network_error: "Can't reach the server",
  timeout: 'The server took too long',
  invalid_input: 'Please check the form',
  invalid_trip: 'Please check the trip',
  location_not_found: 'Place not found',
  no_route: 'No truck route found',
  throttled: 'Too many requests',
  service_rate_limited: 'Service limit reached',
  service_unavailable: 'Service unavailable',
}

/** Red box with a readable backend error and optional retry / dismiss buttons. */
export default function ErrorMessage({ error, onRetry, onDismiss }) {
  return (
    <div className="error-box" role="alert">
      <span className="error-icon" aria-hidden="true">
        !
      </span>
      <div className="error-body">
        <b>{TITLES[error.code] ?? 'Something went wrong'}</b>
        <p>{error.message}</p>
        {(onRetry || onDismiss) && (
          <div className="error-actions">
            {onRetry && (
              <button type="button" onClick={onRetry}>
                Try again
              </button>
            )}
            {onDismiss && (
              <button type="button" className="ghost" onClick={onDismiss}>
                Dismiss
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

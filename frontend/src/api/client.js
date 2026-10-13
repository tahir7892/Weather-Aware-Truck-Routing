/*
 * The one place that talks to the backend. Every backend error has the shape
 * {"error": {"code", "message", "fields"?}} and becomes an ApiError here, so
 * components only ever deal with a readable message.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/+$/, '')

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'error', fields = null } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.fields = fields
  }
}

export async function request(path, { method = 'GET', params, body, signal, timeoutMs = 30000 } = {}) {
  const url = new URL(`${BASE_URL}${path}`, window.location.origin)
  for (const [key, value] of Object.entries(params ?? {})) url.searchParams.set(key, value)

  // Give up after `timeoutMs`, or earlier if the caller cancels (e.g. a newer request replaced this one).
  const timeout = AbortSignal.timeout(timeoutMs)
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout

  let response
  try {
    response = await fetch(url, {
      method,
      signal: combined,
      headers: { Accept: 'application/json', ...(body ? { 'Content-Type': 'application/json' } : {}) },
      body: body ? JSON.stringify(body) : undefined,
    })
  } catch (error) {
    if (timeout.aborted) {
      throw new ApiError('The server took too long to answer. The weather or routing service may be slow; please try again.', {
        code: 'timeout',
      })
    }
    if (error.name === 'AbortError') throw error
    throw new ApiError('Could not reach the server. Check that the backend is running and try again.', {
      code: 'network_error',
    })
  }

  let data = null
  try {
    data = await response.json()
  } catch {
    // Non-JSON body (e.g. a proxy error page); handled below.
  }

  if (!response.ok) {
    const error = data?.error
    throw new ApiError(error?.message || `The server returned an error (${response.status}).`, {
      status: response.status,
      code: error?.code || 'http_error',
      fields: error?.fields || null,
    })
  }
  return data
}

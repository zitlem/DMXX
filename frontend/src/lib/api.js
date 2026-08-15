/**
 * Shared fetch wrapper.
 *
 * `fetch` only rejects on a network failure, so a plain
 * `try { await fetch(...) } catch { ... }` silently treats a 400, 403 or 500
 * as success. Every write in the UI was doing exactly that. `apiFetch` turns a
 * non-2xx response into a thrown ApiError carrying the server's `detail`, so
 * the catch blocks that already exist start doing their job.
 */

export class ApiError extends Error {
  constructor(message, status, url) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.url = url
  }
}

/** Pull FastAPI's `detail` out of an error response, falling back sensibly. */
async function describe(response) {
  try {
    const body = await response.clone().json()
    if (typeof body?.detail === 'string') return body.detail
    if (Array.isArray(body?.detail)) {
      // FastAPI validation errors: [{loc: [...], msg: "..."}]
      const first = body.detail[0]
      if (first?.msg) return `${first.msg}${first.loc ? ` (${first.loc.join('.')})` : ''}`
    }
  } catch (e) {
    // not json, or already consumed - fall through
  }
  return `HTTP ${response.status}`
}

/**
 * fetch, but a non-2xx response throws.
 *
 * @param url      request url
 * @param options  fetch options
 * @param headers  extra headers merged in (typically auth)
 */
export async function apiFetch(url, options = {}, headers = {}) {
  const response = await fetch(url, {
    ...options,
    headers: { ...options.headers, ...headers }
  })

  if (!response.ok) {
    throw new ApiError(await describe(response), response.status, url)
  }
  return response
}

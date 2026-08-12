import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiFetch, apiJson, ApiError } from '../src/lib/api.js'

function stubFetch(response) {
  const spy = vi.fn(async () => response)
  vi.stubGlobal('fetch', spy)
  return spy
}

function jsonResponse(body, { ok = true, status = 200 } = {}) {
  return {
    ok,
    status,
    json: async () => body,
    clone() { return this }
  }
}

beforeEach(() => vi.restoreAllMocks())

describe('apiFetch', () => {
  it('returns the response when the request succeeds', async () => {
    const response = jsonResponse({ ok: true })
    stubFetch(response)

    await expect(apiFetch('/api/thing')).resolves.toBe(response)
  })

  it('merges auth headers into the request', async () => {
    const spy = stubFetch(jsonResponse({}))

    await apiFetch('/api/thing', { method: 'POST', headers: { 'Content-Type': 'application/json' } },
                   { Authorization: 'Bearer token' })

    const [url, options] = spy.mock.calls[0]
    expect(url).toBe('/api/thing')
    expect(options.method).toBe('POST')
    expect(options.headers).toEqual({
      'Content-Type': 'application/json',
      Authorization: 'Bearer token'
    })
  })

  it('throws an ApiError carrying the server detail', async () => {
    stubFetch(jsonResponse({ detail: 'Group not found' }, { ok: false, status: 404 }))

    await expect(apiFetch('/api/groups/9')).rejects.toThrow('Group not found')
  })

  it('exposes the status and url on the error', async () => {
    stubFetch(jsonResponse({ detail: 'nope' }, { ok: false, status: 403 }))

    const error = await apiFetch('/api/x').catch(e => e)

    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(403)
    expect(error.url).toBe('/api/x')
  })

  it('summarises FastAPI validation errors', async () => {
    stubFetch(jsonResponse(
      { detail: [{ loc: ['body', 'value'], msg: 'Input should be a valid integer' }] },
      { ok: false, status: 422 }
    ))

    await expect(apiFetch('/api/x'))
      .rejects.toThrow('Input should be a valid integer (body.value)')
  })

  it('falls back to the status code when the body is not json', async () => {
    stubFetch({
      ok: false,
      status: 500,
      json: async () => { throw new Error('not json') },
      clone() { return this }
    })

    await expect(apiFetch('/api/x')).rejects.toThrow('HTTP 500')
  })

  it('falls back when detail is missing', async () => {
    stubFetch(jsonResponse({ error: 'something' }, { ok: false, status: 400 }))
    await expect(apiFetch('/api/x')).rejects.toThrow('HTTP 400')
  })

  it('lets a network failure propagate unchanged', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch') }))

    await expect(apiFetch('/api/x')).rejects.toThrow('Failed to fetch')
  })

  it('does not consume the body, so callers can still read it', async () => {
    const response = jsonResponse({ id: 1 })
    stubFetch(response)

    const result = await apiFetch('/api/x')
    await expect(result.json()).resolves.toEqual({ id: 1 })
  })
})

describe('apiJson', () => {
  it('decodes a successful response', async () => {
    stubFetch(jsonResponse({ id: 7, name: 'Warm' }))

    await expect(apiJson('/api/groups/7')).resolves.toEqual({ id: 7, name: 'Warm' })
  })

  it('returns null for 204 No Content', async () => {
    stubFetch({ ok: true, status: 204, json: async () => { throw new Error('no body') },
                clone() { return this } })

    await expect(apiJson('/api/x', { method: 'DELETE' })).resolves.toBeNull()
  })

  it('throws on an error response rather than returning the body', async () => {
    stubFetch(jsonResponse({ detail: 'Permission denied' }, { ok: false, status: 403 }))

    await expect(apiJson('/api/x')).rejects.toThrow('Permission denied')
  })
})

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore } from '../src/stores/auth.js'

/** Build a fetch stub that returns the given json for every call. */
function stubFetch(response, { ok = true } = {}) {
  const spy = vi.fn(async () => ({ ok, json: async () => response }))
  vi.stubGlobal('fetch', spy)
  return spy
}

const LOGIN_RESPONSE = {
  access_token: 'jwt-token',
  token_type: 'bearer',
  profile_name: 'Tech',
  allowed_pages: ['faders', 'scenes'],
  allowed_grids: [1, 2],
  allowed_scenes: [5],
  is_admin: false,
  can_park: true,
  can_highlight: true,
  can_bypass: true
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

afterEach(() => {
  localStorage.clear()
})

describe('initial state', () => {
  it('starts logged out with no stored session', () => {
    const auth = useAuthStore()

    expect(auth.authenticated).toBe(false)
    expect(auth.checked).toBe(false)
    expect(auth.token).toBeNull()
    expect(auth.profileName).toBe('')
    expect(auth.allowedPages).toEqual([])
    expect(auth.allowedGrids).toBeNull()
    expect(auth.isAdmin).toBe(false)
  })

  it('rehydrates a stored session from localStorage', () => {
    localStorage.setItem('dmxx_token', 'stored-token')
    localStorage.setItem('dmxx_profile_name', 'Booth')
    localStorage.setItem('dmxx_allowed_pages', JSON.stringify(['faders']))
    localStorage.setItem('dmxx_allowed_grids', JSON.stringify([3]))
    localStorage.setItem('dmxx_is_admin', 'true')

    const auth = useAuthStore()

    expect(auth.token).toBe('stored-token')
    expect(auth.profileName).toBe('Booth')
    expect(auth.allowedPages).toEqual(['faders'])
    expect(auth.allowedGrids).toEqual([3])
    expect(auth.isAdmin).toBe(true)
  })

  it('defaults the feature permissions to allowed', () => {
    const auth = useAuthStore()

    expect(auth.canPark).toBe(true)
    expect(auth.canHighlight).toBe(true)
    expect(auth.canBypass).toBe(true)
  })

  it('honours permissions denied in localStorage', () => {
    localStorage.setItem('dmxx_can_park', 'false')
    localStorage.setItem('dmxx_can_highlight', 'false')
    localStorage.setItem('dmxx_can_bypass', 'false')

    const auth = useAuthStore()

    expect(auth.canPark).toBe(false)
    expect(auth.canHighlight).toBe(false)
    expect(auth.canBypass).toBe(false)
  })
})

describe('access checks', () => {
  it('page access follows allowedPages exactly', () => {
    const auth = useAuthStore()
    auth.allowedPages = ['faders', 'scenes']

    expect(auth.hasPageAccess('faders')).toBe(true)
    expect(auth.hasPageAccess('settings')).toBe(false)
  })

  it('admins reach every grid and scene', () => {
    const auth = useAuthStore()
    auth.isAdmin = true
    auth.allowedGrids = [1]
    auth.allowedScenes = [1]

    expect(auth.hasGridAccess(99)).toBe(true)
    expect(auth.hasSceneAccess(99)).toBe(true)
  })

  it('an empty or null allow-list means everything is allowed', () => {
    const auth = useAuthStore()

    auth.allowedGrids = null
    auth.allowedScenes = null
    expect(auth.hasGridAccess(7)).toBe(true)
    expect(auth.hasSceneAccess(7)).toBe(true)

    auth.allowedGrids = []
    auth.allowedScenes = []
    expect(auth.hasGridAccess(7)).toBe(true)
    expect(auth.hasSceneAccess(7)).toBe(true)
  })

  it('a populated allow-list restricts a non-admin', () => {
    const auth = useAuthStore()
    auth.isAdmin = false
    auth.allowedGrids = [1, 2]
    auth.allowedScenes = [5]

    expect(auth.hasGridAccess(1)).toBe(true)
    expect(auth.hasGridAccess(3)).toBe(false)
    expect(auth.hasSceneAccess(5)).toBe(true)
    expect(auth.hasSceneAccess(6)).toBe(false)
  })
})

describe('login', () => {
  it('stores the session in state and localStorage', async () => {
    stubFetch(LOGIN_RESPONSE)
    const auth = useAuthStore()

    await expect(auth.login('secret')).resolves.toBe(true)

    expect(auth.authenticated).toBe(true)
    expect(auth.token).toBe('jwt-token')
    expect(auth.profileName).toBe('Tech')
    expect(auth.allowedPages).toEqual(['faders', 'scenes'])
    expect(localStorage.getItem('dmxx_token')).toBe('jwt-token')
    expect(JSON.parse(localStorage.getItem('dmxx_allowed_pages')))
      .toEqual(['faders', 'scenes'])
    expect(localStorage.getItem('dmxx_is_admin')).toBe('false')
  })

  it('posts the password as json', async () => {
    const fetchSpy = stubFetch(LOGIN_RESPONSE)
    const auth = useAuthStore()

    await auth.login('secret')

    const [url, options] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect(options.method).toBe('POST')
    expect(JSON.parse(options.body)).toEqual({ password: 'secret' })
  })

  it('clears a previous logout flag', async () => {
    localStorage.setItem('dmxx_logged_out', 'true')
    stubFetch(LOGIN_RESPONSE)
    const auth = useAuthStore()

    await auth.login('secret')

    expect(localStorage.getItem('dmxx_logged_out')).toBeNull()
  })

  it('raises the server detail on a rejected password', async () => {
    stubFetch({ detail: 'Incorrect password' }, { ok: false })
    const auth = useAuthStore()

    await expect(auth.login('wrong')).rejects.toThrow('Incorrect password')
    expect(auth.authenticated).toBe(false)
    expect(localStorage.getItem('dmxx_token')).toBeNull()
  })

  it('falls back to a generic message when none is given', async () => {
    stubFetch({}, { ok: false })
    const auth = useAuthStore()

    await expect(auth.login('wrong')).rejects.toThrow('Login failed')
  })

  it('records denied permissions from the response', async () => {
    stubFetch({ ...LOGIN_RESPONSE, can_park: false, can_highlight: false })
    const auth = useAuthStore()

    await auth.login('secret')

    expect(auth.canPark).toBe(false)
    expect(auth.canHighlight).toBe(false)
    expect(auth.canBypass).toBe(true)
  })
})

describe('logout', () => {
  it('clears state and stored session, and sets the logout flag', async () => {
    stubFetch(LOGIN_RESPONSE)
    const auth = useAuthStore()
    await auth.login('secret')

    auth.logout()

    expect(auth.authenticated).toBe(false)
    expect(auth.token).toBeNull()
    expect(auth.profileName).toBe('')
    expect(auth.allowedPages).toEqual([])
    expect(auth.isAdmin).toBe(false)
    expect(localStorage.getItem('dmxx_logged_out')).toBe('true')

    for (const key of ['dmxx_token', 'dmxx_profile_name', 'dmxx_allowed_pages',
                       'dmxx_allowed_grids', 'dmxx_allowed_scenes',
                       'dmxx_is_admin', 'dmxx_can_park']) {
      expect(localStorage.getItem(key)).toBeNull()
    }
  })

  it('restores the permissive permission defaults', () => {
    const auth = useAuthStore()
    auth.canPark = false

    auth.logout()

    expect(auth.canPark).toBe(true)
    expect(auth.canHighlight).toBe(true)
    expect(auth.canBypass).toBe(true)
  })
})

describe('checkAuth', () => {
  it('adopts the profile the server reports', async () => {
    stubFetch({
      authenticated: true,
      ip: '10.0.0.5',
      profile_name: 'Booth',
      allowed_pages: ['faders'],
      allowed_grids: [2],
      allowed_scenes: null,
      is_admin: true,
      can_park: false
    })
    const auth = useAuthStore()

    await expect(auth.checkAuth()).resolves.toBe(true)

    expect(auth.authenticated).toBe(true)
    expect(auth.clientIp).toBe('10.0.0.5')
    expect(auth.profileName).toBe('Booth')
    expect(auth.allowedGrids).toEqual([2])
    expect(auth.isAdmin).toBe(true)
    expect(auth.canPark).toBe(false)
    expect(auth.checked).toBe(true)
  })

  it('sends the bearer token when one is stored', async () => {
    localStorage.setItem('dmxx_token', 'stored-token')
    const fetchSpy = stubFetch({ authenticated: true, ip: '1.2.3.4' })
    const auth = useAuthStore()

    await auth.checkAuth()

    const [, options] = fetchSpy.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer stored-token')
  })

  it('stays logged out after an explicit logout, but still reports the ip', async () => {
    localStorage.setItem('dmxx_logged_out', 'true')
    const fetchSpy = stubFetch({ authenticated: true, ip: '10.0.0.9' })
    const auth = useAuthStore()

    await expect(auth.checkAuth()).resolves.toBe(false)

    expect(auth.authenticated).toBe(false)
    expect(auth.isAdmin).toBe(false)
    expect(auth.clientIp).toBe('10.0.0.9')
    expect(fetchSpy.mock.calls[0][0]).toBe('/api/auth/status')
  })

  it('does not persist anything when the server says unauthenticated', async () => {
    stubFetch({ authenticated: false, ip: '10.0.0.9' })
    const auth = useAuthStore()

    await expect(auth.checkAuth()).resolves.toBe(false)

    expect(auth.checked).toBe(true)
    expect(localStorage.getItem('dmxx_allowed_pages')).toBeNull()
  })

  it('treats a network failure as unauthenticated and drops admin', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('offline')
    }))
    const auth = useAuthStore()
    auth.isAdmin = true

    await expect(auth.checkAuth()).resolves.toBe(false)

    expect(auth.checked).toBe(true)
    expect(auth.isAdmin).toBe(false)
  })
})

describe('auth headers', () => {
  it('are empty without a token', () => {
    expect(useAuthStore().getAuthHeaders()).toEqual({})
  })

  it('carry the bearer token when present', () => {
    localStorage.setItem('dmxx_token', 'jwt-token')
    expect(useAuthStore().getAuthHeaders())
      .toEqual({ Authorization: 'Bearer jwt-token' })
  })
})

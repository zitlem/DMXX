import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import router from '../src/router.js'
import { useAuthStore } from '../src/stores/auth.js'

/**
 * Exercises router.beforeEach - the app's authorization gate.
 *
 * Each route is re-registered under its existing name with a stub component,
 * so navigation never pulls in the real .vue component tree. Every test starts
 * parked on /unauthorized (reachable by any signed-in profile and carrying no
 * page permission), so no test navigates to the route it is already on.
 */
const STUB = { render: () => null }

const ROUTES = [
  ['Login', '/login', { requiresAuth: false }],
  ['Faders', '/faders', { requiresAuth: true, page: 'faders' }],
  ['Scenes', '/scenes', { requiresAuth: true, page: 'scenes' }],
  ['Settings', '/settings', { requiresAuth: true, page: 'settings' }],
  ['Unauthorized', '/unauthorized', { requiresAuth: true }]
]

function stubRoutes() {
  for (const [name, path, meta] of ROUTES) {
    router.addRoute({ name, path, meta, component: STUB })
  }
}

/** Navigate, tolerating the redirects the guard performs. */
async function go(path) {
  try {
    await router.push(path)
  } catch (error) {
    if (error?.type !== 4) throw error   // 4 = redirected by a guard
  }
  return router.currentRoute.value.path
}

function stubFetch(response) {
  const spy = vi.fn(async () => ({ ok: true, json: async () => response }))
  vi.stubGlobal('fetch', spy)
  return spy
}

beforeEach(async () => {
  localStorage.clear()
  setActivePinia(createPinia())
  stubRoutes()

  // Park on a route every signed-in profile may see, without touching fetch
  const auth = useAuthStore()
  auth.checked = true
  auth.authenticated = true
  auth.allowedPages = []
  await router.replace('/unauthorized').catch(() => {})
})

afterEach(() => {
  localStorage.clear()
})

describe('authentication gate', () => {
  it('sends an anonymous visitor to the login page', async () => {
    stubFetch({ authenticated: false })
    const auth = useAuthStore()
    auth.authenticated = false

    expect(await go('/faders')).toBe('/login')
  })

  it('checks auth once when it has not been checked yet', async () => {
    const fetchSpy = stubFetch({
      authenticated: true, ip: '1.2.3.4', allowed_pages: ['faders']
    })
    const auth = useAuthStore()
    auth.checked = false

    expect(await go('/faders')).toBe('/faders')
    expect(auth.checked).toBe(true)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })

  it('adopts the profile the check returns', async () => {
    stubFetch({
      authenticated: true, ip: '1.2.3.4', allowed_pages: ['scenes']
    })
    const auth = useAuthStore()
    auth.checked = false

    expect(await go('/faders')).toBe('/unauthorized')
    expect(auth.allowedPages).toEqual(['scenes'])
  })

  it('does not re-check auth on later navigations', async () => {
    const fetchSpy = stubFetch({ authenticated: true })
    const auth = useAuthStore()
    auth.allowedPages = ['faders', 'scenes']

    await go('/faders')
    await go('/scenes')

    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('lets an anonymous visitor reach the login page', async () => {
    stubFetch({ authenticated: false })
    useAuthStore().authenticated = false

    expect(await go('/login')).toBe('/login')
  })
})

describe('page permissions', () => {
  beforeEach(() => {
    stubFetch({ authenticated: true })
    useAuthStore().allowedPages = ['faders']
  })

  it('allows a page the profile is granted', async () => {
    expect(await go('/faders')).toBe('/faders')
  })

  it('diverts a page the profile lacks', async () => {
    expect(await go('/settings')).toBe('/unauthorized')
  })

  it('lets the unauthorized page itself through', async () => {
    await go('/faders')
    expect(await go('/unauthorized')).toBe('/unauthorized')
  })

  it('re-evaluates when the profile gains a page', async () => {
    expect(await go('/scenes')).toBe('/unauthorized')

    useAuthStore().allowedPages = ['faders', 'scenes']
    expect(await go('/scenes')).toBe('/scenes')
  })
})

describe('already signed in', () => {
  it('bounces away from the login page to the first allowed page', async () => {
    stubFetch({ authenticated: true })
    const auth = useAuthStore()
    auth.allowedPages = ['scenes', 'faders']

    await go('/scenes')
    expect(await go('/login')).toBe('/scenes')
  })

  it('a profile with no pages ends up on the unauthorized page', async () => {
    // The guard sends it to /faders, which it may not see either
    stubFetch({ authenticated: true })
    const auth = useAuthStore()
    auth.allowedPages = []

    await go('/scenes')
    expect(await go('/login')).toBe('/unauthorized')
  })
})

import { describe, it, expect } from 'vitest'
import router from '../src/router.js'
import { PAGE_IDS } from '../src/config/pages.js'

/**
 * These tests inspect the route table only. Route components are lazily
 * imported, so nothing here mounts a component or pulls in the component tree.
 */
const routes = router.getRoutes()

function routeFor(path) {
  return routes.find((route) => route.path === path)
}

describe('route table', () => {
  it('exposes the pages the nav links to', () => {
    for (const path of ['/login', '/faders', '/fixtures', '/patch', '/io',
                        '/mapping', '/groups', '/scenes', '/settings',
                        '/remote-api', '/help', '/unauthorized', '/monitor',
                        '/control-flow', '/midi']) {
      expect(routeFor(path), `missing route ${path}`).toBeDefined()
    }
  })

  it('redirects the root to the faders page', () => {
    expect(routeFor('/').redirect).toBe('/faders')
  })

  it('leaves login open and protects everything else', () => {
    expect(routeFor('/login').meta.requiresAuth).toBe(false)

    for (const route of routes) {
      if (['/login', '/'].includes(route.path)) continue
      expect(route.meta.requiresAuth, `${route.path} is unprotected`).toBe(true)
    }
  })

  it('every page permission refers to a real page id', () => {
    for (const route of routes) {
      if (!route.meta.page) continue
      expect(PAGE_IDS, `${route.path} -> ${route.meta.page}`)
        .toContain(route.meta.page)
    }
  })

  it('guards each protected route with a page permission', () => {
    const exempt = new Set(['/login', '/', '/unauthorized'])

    for (const route of routes) {
      if (exempt.has(route.path)) continue
      expect(route.meta.page, `${route.path} has no page permission`)
        .toBeTruthy()
    }
  })

  it('groups the io sub-pages under the io permission', () => {
    expect(routeFor('/io').meta.page).toBe('io')
    expect(routeFor('/mapping').meta.page).toBe('io')
    expect(routeFor('/control-flow').meta.page).toBe('io')
  })

  it('puts the remote api behind the settings permission', () => {
    expect(routeFor('/remote-api').meta.page).toBe('settings')
  })

  it('lets an authenticated user reach the unauthorized page', () => {
    const route = routeFor('/unauthorized')
    expect(route.meta.requiresAuth).toBe(true)
    expect(route.meta.page).toBeUndefined()
  })

  it('names every route it exposes', () => {
    for (const route of routes) {
      if (route.path === '/') continue      // pure redirect
      expect(route.name, `${route.path} has no name`).toBeTruthy()
    }
  })

  it('has no duplicate paths or names', () => {
    const paths = routes.map((route) => route.path)
    const names = routes.map((route) => route.name).filter(Boolean)

    expect(new Set(paths).size).toBe(paths.length)
    expect(new Set(names).size).toBe(names.length)
  })
})

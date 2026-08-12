import { describe, it, expect } from 'vitest'
import { PAGES, PAGE_IDS, getPageLabel } from '../src/config/pages.js'

describe('page registry', () => {
  it('every entry has an id and a name', () => {
    for (const page of PAGES) {
      expect(Object.keys(page).sort()).toEqual(['id', 'name'])
      expect(page.id).toBeTruthy()
      expect(page.name).toBeTruthy()
    }
  })

  it('ids are unique lowercase slugs', () => {
    expect(new Set(PAGE_IDS).size).toBe(PAGE_IDS.length)
    for (const id of PAGE_IDS) {
      expect(id).toBe(id.toLowerCase())
      expect(id).not.toContain(' ')
    }
  })

  it('PAGE_IDS mirrors PAGES', () => {
    expect(PAGE_IDS).toEqual(PAGES.map((page) => page.id))
  })

  it('covers the pages the profile editor offers', () => {
    for (const id of ['faders', 'scenes', 'fixtures', 'patch', 'io',
                      'groups', 'midi', 'settings', 'monitor', 'help']) {
      expect(PAGE_IDS).toContain(id)
    }
  })
})

describe('getPageLabel', () => {
  it('returns the display name for a known page', () => {
    expect(getPageLabel('io')).toBe('I/O')
    expect(getPageLabel('monitor')).toBe('Network Monitor')
  })

  it('falls back to the id for an unknown page', () => {
    expect(getPageLabel('does-not-exist')).toBe('does-not-exist')
  })

  it('does not throw on empty input', () => {
    expect(getPageLabel(undefined)).toBeUndefined()
    expect(getPageLabel('')).toBe('')
  })
})

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useThemeStore } from '../src/stores/theme.js'

const LIGHT_PRESET = {
  bgPrimary: '#f5f5f5',
  bgSecondary: '#ffffff',
  accent: '#e94560',
  textPrimary: '#212121'
}

function stubFetch(responder) {
  const spy = vi.fn(async (url, options) => ({
    ok: true,
    json: async () => responder(url, options)
  }))
  vi.stubGlobal('fetch', spy)
  return spy
}

function cssVar(name) {
  return document.documentElement.style.getPropertyValue(name)
}

beforeEach(() => {
  localStorage.clear()
  document.documentElement.style.cssText = ''
  setActivePinia(createPinia())
})

afterEach(() => {
  localStorage.clear()
})

describe('defaults', () => {
  it('starts on the dark preset', () => {
    const theme = useThemeStore()

    expect(theme.themeData.type).toBe('preset')
    expect(theme.themeData.presetName).toBe('dark')
    expect(theme.themeData.colors.bgPrimary).toBe('#1a1a2e')
    expect(theme.loaded).toBe(false)
  })

  it('reports no unsaved changes before anything is loaded', () => {
    expect(useThemeStore().hasUnsavedChanges).toBe(false)
  })
})

describe('applyTheme', () => {
  it('writes every colour to its css variable', () => {
    const theme = useThemeStore()

    theme.applyTheme()

    expect(cssVar('--bg-primary')).toBe('#1a1a2e')
    expect(cssVar('--accent')).toBe('#e94560')
    expect(cssVar('--indicator-remote')).toBe('#00bcd4')
    expect(cssVar('--fader-fill')).toBe('#e94560')
  })

  it('skips colours that are missing', () => {
    const theme = useThemeStore()
    theme.themeData.colors = { accent: '#123456' }

    theme.applyTheme()

    expect(cssVar('--accent')).toBe('#123456')
    expect(cssVar('--bg-primary')).toBe('')
  })
})

describe('presets', () => {
  it('setPreset swaps the palette and persists it', async () => {
    const fetchSpy = stubFetch(() => ({}))
    const theme = useThemeStore()
    theme.presets = { light: LIGHT_PRESET }

    theme.setPreset('light')

    expect(theme.themeData.type).toBe('preset')
    expect(theme.themeData.presetName).toBe('light')
    expect(theme.themeData.colors.bgPrimary).toBe('#f5f5f5')
    expect(cssVar('--bg-primary')).toBe('#f5f5f5')

    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalled())
    const [url, options] = fetchSpy.mock.calls.at(-1)
    expect(url).toBe('/api/settings')
    expect(JSON.parse(options.body).key).toBe('theme')
  })

  it('setPreset ignores an unknown preset name', () => {
    const theme = useThemeStore()
    theme.presets = { light: LIGHT_PRESET }

    theme.setPreset('neon')

    expect(theme.themeData.presetName).toBe('dark')
  })

  it('copies the preset rather than aliasing it', () => {
    const theme = useThemeStore()
    theme.presets = { light: { ...LIGHT_PRESET } }
    stubFetch(() => ({}))

    theme.setPreset('light')
    theme.themeData.colors.accent = '#000000'

    expect(theme.presets.light.accent).toBe('#e94560')
  })

  it('loadPresets stores what the server returns', async () => {
    stubFetch(() => ({ presets: { dark: {}, light: LIGHT_PRESET } }))
    const theme = useThemeStore()

    await theme.loadPresets()

    expect(Object.keys(theme.presets)).toEqual(['dark', 'light'])
  })

  it('loadPresets survives a failing request', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    const theme = useThemeStore()

    await theme.loadPresets()

    expect(theme.presets).toEqual({})
  })
})

describe('custom colours', () => {
  it('switches the theme to custom and caches the change', () => {
    const theme = useThemeStore()

    theme.setCustomColor('accent', '#ff0000')

    expect(theme.themeData.type).toBe('custom')
    expect(theme.themeData.presetName).toBeNull()
    expect(theme.themeData.colors.accent).toBe('#ff0000')
    expect(cssVar('--accent')).toBe('#ff0000')

    const cached = JSON.parse(localStorage.getItem('dmxx_theme_cache'))
    expect(cached.colors.accent).toBe('#ff0000')
  })

  it('does not save to the server until asked', () => {
    const fetchSpy = stubFetch(() => ({}))
    const theme = useThemeStore()

    theme.setCustomColor('accent', '#ff0000')
    expect(fetchSpy).not.toHaveBeenCalled()

    theme.saveCustomTheme()
    expect(fetchSpy).toHaveBeenCalled()
  })
})

describe('unsaved change tracking', () => {
  it('is true once the live theme diverges from the saved one', async () => {
    stubFetch(() => ({ value: JSON.stringify({
      type: 'preset', presetName: 'dark', colors: { accent: '#e94560' }
    }) }))
    const theme = useThemeStore()
    await theme.loadTheme()

    expect(theme.hasUnsavedChanges).toBe(false)

    theme.setCustomColor('accent', '#00ff00')
    expect(theme.hasUnsavedChanges).toBe(true)
  })

  it('clears again after a save', async () => {
    stubFetch(() => ({ value: JSON.stringify({
      type: 'preset', presetName: 'dark', colors: { accent: '#e94560' }
    }) }))
    const theme = useThemeStore()
    await theme.loadTheme()
    theme.setCustomColor('accent', '#00ff00')

    await theme.saveTheme()

    expect(theme.hasUnsavedChanges).toBe(false)
  })
})

describe('loadTheme', () => {
  it('adopts the server theme when there is no cache', async () => {
    stubFetch(() => ({ value: JSON.stringify({
      type: 'preset', presetName: 'light', colors: LIGHT_PRESET
    }) }))
    const theme = useThemeStore()

    await theme.loadTheme()

    expect(theme.themeData.presetName).toBe('light')
    expect(theme.loaded).toBe(true)
    expect(cssVar('--bg-primary')).toBe('#f5f5f5')
  })

  it('keeps cached local edits that differ from the server', async () => {
    const cached = {
      type: 'custom', presetName: null, colors: { accent: '#abcdef' }
    }
    localStorage.setItem('dmxx_theme_cache', JSON.stringify(cached))
    stubFetch(() => ({ value: JSON.stringify({
      type: 'preset', presetName: 'dark', colors: { accent: '#e94560' }
    }) }))
    const theme = useThemeStore()

    await theme.loadTheme()

    expect(theme.themeData.colors.accent).toBe('#abcdef')
    expect(theme.hasUnsavedChanges).toBe(true)
  })

  it('tolerates an unparseable server theme', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    stubFetch(() => ({ value: 'not json' }))
    const theme = useThemeStore()

    await theme.loadTheme()

    expect(theme.themeData.presetName).toBe('dark')
    expect(theme.loaded).toBe(true)
  })

  it('falls back to the defaults when the request fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    const theme = useThemeStore()

    await theme.loadTheme()

    expect(theme.loaded).toBe(true)
    expect(theme.hasUnsavedChanges).toBe(false)
    expect(cssVar('--bg-primary')).toBe('#1a1a2e')
  })
})

describe('cached theme', () => {
  it('loadCachedTheme applies the cache synchronously', () => {
    localStorage.setItem('dmxx_theme_cache', JSON.stringify({
      type: 'custom', presetName: null, colors: { accent: '#101010' }
    }))
    const theme = useThemeStore()

    theme.loadCachedTheme()

    expect(theme.themeData.colors.accent).toBe('#101010')
    expect(cssVar('--accent')).toBe('#101010')
  })

  it('ignores a corrupt cache', () => {
    localStorage.setItem('dmxx_theme_cache', 'not json')
    const theme = useThemeStore()

    expect(() => theme.loadCachedTheme()).not.toThrow()
    expect(theme.themeData.presetName).toBe('dark')
  })

  it('does nothing when there is no cache', () => {
    const theme = useThemeStore()
    theme.loadCachedTheme()
    expect(theme.themeData.presetName).toBe('dark')
  })
})

describe('reset', () => {
  it('returns to the dark preset and saves', async () => {
    const fetchSpy = stubFetch(() => ({}))
    const theme = useThemeStore()
    theme.setCustomColor('accent', '#ff0000')

    theme.resetToDefault()

    expect(theme.themeData.type).toBe('preset')
    expect(theme.themeData.presetName).toBe('dark')
    expect(theme.themeData.colors.accent).toBe('#e94560')
    expect(cssVar('--accent')).toBe('#e94560')
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalled())
  })
})

describe('authenticated requests', () => {
  it('attaches the bearer token to theme requests', async () => {
    localStorage.setItem('dmxx_token', 'jwt-token')
    const fetchSpy = stubFetch(() => ({ presets: {} }))
    const theme = useThemeStore()

    await theme.loadPresets()

    const [, options] = fetchSpy.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer jwt-token')
  })
})

// ---------------------------------------------------------------------------
// Server-side failures
//
// fetch resolves for a 500, so before apiFetch these paths parsed an error
// body as if it were a theme.
// ---------------------------------------------------------------------------
function stubErrorResponse(status = 500, body = { detail: 'boom' }) {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: false,
    status,
    json: async () => body,
    clone() { return this }
  })))
}

describe('error responses', () => {
  it('loadTheme falls back to the defaults on a 500', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    stubErrorResponse()
    const theme = useThemeStore()

    await theme.loadTheme()

    expect(theme.loaded).toBe(true)
    expect(theme.themeData.presetName).toBe('dark')
    expect(cssVar('--bg-primary')).toBe('#1a1a2e')
  })

  it('loadPresets keeps the presets empty on a 500', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    stubErrorResponse()
    const theme = useThemeStore()

    await theme.loadPresets()

    expect(theme.presets).toEqual({})
  })

  it('a rejected save leaves the theme marked as unsaved', async () => {
    stubFetch(() => ({ value: JSON.stringify({
      type: 'preset', presetName: 'dark', colors: { accent: '#e94560' }
    }) }))
    const theme = useThemeStore()
    await theme.loadTheme()
    theme.setCustomColor('accent', '#00ff00')
    expect(theme.hasUnsavedChanges).toBe(true)

    vi.spyOn(console, 'error').mockImplementation(() => {})
    stubErrorResponse(403, { detail: 'Permission denied' })
    await theme.saveTheme()

    // The change was not persisted, so it must still show as unsaved
    expect(theme.hasUnsavedChanges).toBe(true)
  })
})

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAuthStore } from './auth.js'

// Default dark theme colors
const DARK_THEME = {
  bgPrimary: "#1a1a2e",
  bgSecondary: "#16213e",
  bgTertiary: "#0f3460",
  textPrimary: "#eeeeee",
  textSecondary: "#aaaaaa",
  accent: "#e94560",
  accentHover: "#ff6b6b",
  success: "#4ade80",
  warning: "#fbbf24",
  error: "#f87171",
  border: "#2a2a4a",
  faderBg: "#2a2a4a",
  faderFill: "#e94560",
  indicatorRemote: "#00bcd4",
  indicatorLocal: "#4caf50",
  indicatorGroup: "#4ade80"
}

export const useThemeStore = defineStore('theme', () => {
  const themeData = ref({
    type: 'preset',
    presetName: 'dark',
    colors: { ...DARK_THEME }
  })
  const savedThemeData = ref(null)  // Track what was last saved to detect unsaved changes
  const presets = ref({})
  const loaded = ref(false)

  // Check if there are unsaved theme changes
  const hasUnsavedChanges = computed(() => {
    if (!savedThemeData.value) return false
    return JSON.stringify(themeData.value) !== JSON.stringify(savedThemeData.value)
  })

  async function fetchWithAuth(url, options = {}) {
    const authStore = useAuthStore()
    options.headers = {
      ...options.headers,
      ...authStore.getAuthHeaders()
    }
    return fetch(url, options)
  }

  async function loadTheme() {
    try {
      const response = await fetchWithAuth('/api/settings/theme')
      const data = await response.json()

      // Parse server theme
      let serverTheme = null
      if (data.value) {
        try {
          serverTheme = JSON.parse(data.value)
        } catch (e) {
          console.warn('Could not parse theme, using default:', e)
        }
      }

      // Set savedThemeData to what's on the server (for unsaved changes detection)
      savedThemeData.value = serverTheme
        ? JSON.parse(JSON.stringify(serverTheme))
        : JSON.parse(JSON.stringify(themeData.value))

      // Check if we have cached changes that differ from server
      const cached = localStorage.getItem('dmxx_theme_cache')
      if (cached) {
        const cachedTheme = JSON.parse(cached)
        // If cache differs from server, keep the cached version (unsaved changes)
        if (JSON.stringify(cachedTheme) !== JSON.stringify(serverTheme)) {
          themeData.value = cachedTheme
        } else if (serverTheme) {
          themeData.value = serverTheme
        }
      } else if (serverTheme) {
        themeData.value = serverTheme
      }

      applyTheme()
      cacheTheme()
      loaded.value = true
    } catch (e) {
      console.error('Failed to load theme:', e)
      applyTheme()
      savedThemeData.value = JSON.parse(JSON.stringify(themeData.value))
      loaded.value = true
    }
  }

  async function loadPresets() {
    try {
      const response = await fetchWithAuth('/api/settings/theme/presets')
      const data = await response.json()
      presets.value = data.presets
    } catch (e) {
      console.error('Failed to load theme presets:', e)
    }
  }

  async function saveTheme() {
    try {
      await fetchWithAuth('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          key: 'theme',
          value: JSON.stringify(themeData.value)
        })
      })
      cacheTheme()
      // Update saved state to mark as no longer having unsaved changes
      savedThemeData.value = JSON.parse(JSON.stringify(themeData.value))
    } catch (e) {
      console.error('Failed to save theme:', e)
    }
  }

  function cacheTheme() {
    localStorage.setItem('dmxx_theme_cache', JSON.stringify(themeData.value))
  }

  function applyTheme() {
    const colors = themeData.value.colors
    const root = document.documentElement

    // Map camelCase keys to CSS variable names
    const varMapping = {
      bgPrimary: '--bg-primary',
      bgSecondary: '--bg-secondary',
      bgTertiary: '--bg-tertiary',
      textPrimary: '--text-primary',
      textSecondary: '--text-secondary',
      accent: '--accent',
      accentHover: '--accent-hover',
      success: '--success',
      warning: '--warning',
      error: '--error',
      border: '--border',
      faderBg: '--fader-bg',
      faderFill: '--fader-fill',
      indicatorRemote: '--indicator-remote',
      indicatorLocal: '--indicator-local',
      indicatorGroup: '--indicator-group'
    }

    Object.entries(varMapping).forEach(([key, cssVar]) => {
      if (colors[key]) {
        root.style.setProperty(cssVar, colors[key])
      }
    })
  }

  function setPreset(presetName) {
    if (presets.value[presetName]) {
      themeData.value = {
        type: 'preset',
        presetName: presetName,
        colors: { ...presets.value[presetName] }
      }
      applyTheme()
      saveTheme()
    }
  }

  function setCustomColor(colorKey, colorValue) {
    themeData.value.type = 'custom'
    themeData.value.presetName = null
    themeData.value.colors[colorKey] = colorValue
    applyTheme()
    cacheTheme()  // Persist to localStorage so changes survive navigation
  }

  function saveCustomTheme() {
    saveTheme()
  }

  function resetToDefault() {
    themeData.value = {
      type: 'preset',
      presetName: 'dark',
      colors: { ...DARK_THEME }
    }
    applyTheme()
    saveTheme()
  }

  // Try to load cached theme immediately for faster initial render
  function loadCachedTheme() {
    try {
      const cached = localStorage.getItem('dmxx_theme_cache')
      if (cached) {
        const parsed = JSON.parse(cached)
        themeData.value = parsed
        applyTheme()
      }
    } catch (e) {
      // Ignore cache errors
    }
  }

  return {
    themeData,
    presets,
    loaded,
    hasUnsavedChanges,
    loadTheme,
    loadPresets,
    saveTheme,
    applyTheme,
    setPreset,
    setCustomColor,
    saveCustomTheme,
    resetToDefault,
    loadCachedTheme
  }
})

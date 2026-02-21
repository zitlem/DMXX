import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const authenticated = ref(false)
  const checked = ref(false)
  const token = ref(localStorage.getItem('dmxx_token') || null)
  const clientIp = ref('')

  // Profile-related state
  const profileName = ref(localStorage.getItem('dmxx_profile_name') || '')
  const allowedPages = ref(JSON.parse(localStorage.getItem('dmxx_allowed_pages') || '[]'))
  const allowedGrids = ref(JSON.parse(localStorage.getItem('dmxx_allowed_grids') || 'null'))
  const allowedScenes = ref(JSON.parse(localStorage.getItem('dmxx_allowed_scenes') || 'null'))
  const isAdmin = ref(localStorage.getItem('dmxx_is_admin') === 'true')

  // Feature permissions
  const canPark = ref(localStorage.getItem('dmxx_can_park') !== 'false')
  const canHighlight = ref(localStorage.getItem('dmxx_can_highlight') !== 'false')
  const canBypass = ref(localStorage.getItem('dmxx_can_bypass') !== 'false')

  function hasPageAccess(page) {
    return allowedPages.value.includes(page)
  }

  function hasGridAccess(gridId) {
    // Admins see all grids
    if (isAdmin.value) return true
    // Empty/null means all grids allowed
    if (!allowedGrids.value || allowedGrids.value.length === 0) return true
    return allowedGrids.value.includes(gridId)
  }

  function hasSceneAccess(sceneId) {
    // Admins see all scenes
    if (isAdmin.value) return true
    // Empty/null means all scenes allowed
    if (!allowedScenes.value || allowedScenes.value.length === 0) return true
    return allowedScenes.value.includes(sceneId)
  }

  async function checkAuth() {
    const loggedOut = localStorage.getItem('dmxx_logged_out')

    // If user explicitly logged out, stay logged out (but still get IP for display)
    if (loggedOut) {
      try {
        const response = await fetch('/api/auth/status')
        const data = await response.json()
        clientIp.value = data.ip  // Still get IP for display on login page
      } catch (e) {}
      checked.value = true
      authenticated.value = false
      isAdmin.value = false  // Reset admin state when logged out
      return false
    }

    try {
      const headers = {}
      if (token.value) {
        headers['Authorization'] = `Bearer ${token.value}`
      }

      const response = await fetch('/api/auth/status', { headers })
      const data = await response.json()

      authenticated.value = data.authenticated
      clientIp.value = data.ip
      checked.value = true

      if (data.authenticated) {
        profileName.value = data.profile_name || ''
        allowedPages.value = data.allowed_pages || []
        allowedGrids.value = data.allowed_grids || null
        allowedScenes.value = data.allowed_scenes || null
        isAdmin.value = data.is_admin || false
        canPark.value = data.can_park !== false
        canHighlight.value = data.can_highlight !== false
        canBypass.value = data.can_bypass !== false

        // Persist to localStorage
        localStorage.setItem('dmxx_profile_name', profileName.value)
        localStorage.setItem('dmxx_allowed_pages', JSON.stringify(allowedPages.value))
        localStorage.setItem('dmxx_allowed_grids', JSON.stringify(allowedGrids.value))
        localStorage.setItem('dmxx_allowed_scenes', JSON.stringify(allowedScenes.value))
        localStorage.setItem('dmxx_is_admin', String(isAdmin.value))
        localStorage.setItem('dmxx_can_park', String(canPark.value))
        localStorage.setItem('dmxx_can_highlight', String(canHighlight.value))
        localStorage.setItem('dmxx_can_bypass', String(canBypass.value))
      }

      return data.authenticated
    } catch (e) {
      console.error('Auth check failed:', e)
      checked.value = true
      // Reset admin state on auth failure
      isAdmin.value = false
      return false
    }
  }

  async function login(password) {
    try {
      const response = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password })
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Login failed')
      }

      const data = await response.json()

      // Clear logout flag on successful login
      localStorage.removeItem('dmxx_logged_out')

      token.value = data.access_token
      profileName.value = data.profile_name
      allowedPages.value = data.allowed_pages
      allowedGrids.value = data.allowed_grids
      allowedScenes.value = data.allowed_scenes
      isAdmin.value = data.is_admin
      canPark.value = data.can_park !== false
      canHighlight.value = data.can_highlight !== false
      canBypass.value = data.can_bypass !== false

      localStorage.setItem('dmxx_token', data.access_token)
      localStorage.setItem('dmxx_profile_name', data.profile_name)
      localStorage.setItem('dmxx_allowed_pages', JSON.stringify(data.allowed_pages))
      localStorage.setItem('dmxx_allowed_grids', JSON.stringify(data.allowed_grids))
      localStorage.setItem('dmxx_allowed_scenes', JSON.stringify(data.allowed_scenes))
      localStorage.setItem('dmxx_is_admin', String(data.is_admin))
      localStorage.setItem('dmxx_can_park', String(canPark.value))
      localStorage.setItem('dmxx_can_highlight', String(canHighlight.value))
      localStorage.setItem('dmxx_can_bypass', String(canBypass.value))

      authenticated.value = true

      return true
    } catch (e) {
      throw e
    }
  }

  function logout() {
    // Set logout flag to prevent IP auto-login
    localStorage.setItem('dmxx_logged_out', 'true')

    token.value = null
    profileName.value = ''
    allowedPages.value = []
    allowedGrids.value = null
    allowedScenes.value = null
    isAdmin.value = false
    canPark.value = true
    canHighlight.value = true
    canBypass.value = true

    localStorage.removeItem('dmxx_token')
    localStorage.removeItem('dmxx_profile_name')
    localStorage.removeItem('dmxx_allowed_pages')
    localStorage.removeItem('dmxx_allowed_grids')
    localStorage.removeItem('dmxx_allowed_scenes')
    localStorage.removeItem('dmxx_is_admin')
    localStorage.removeItem('dmxx_can_park')
    localStorage.removeItem('dmxx_can_highlight')
    localStorage.removeItem('dmxx_can_bypass')

    authenticated.value = false
  }

  function getAuthHeaders() {
    if (token.value) {
      return { 'Authorization': `Bearer ${token.value}` }
    }
    return {}
  }

  return {
    authenticated,
    checked,
    token,
    clientIp,
    profileName,
    allowedPages,
    allowedGrids,
    allowedScenes,
    isAdmin,
    canPark,
    canHighlight,
    canBypass,
    hasPageAccess,
    hasGridAccess,
    hasSceneAccess,
    checkAuth,
    login,
    logout,
    getAuthHeaders
  }
})

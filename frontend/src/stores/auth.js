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
  const isAdmin = ref(localStorage.getItem('dmxx_is_admin') === 'true')

  function hasPageAccess(page) {
    return allowedPages.value.includes(page)
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
        isAdmin.value = data.is_admin || false

        // Persist to localStorage
        localStorage.setItem('dmxx_profile_name', profileName.value)
        localStorage.setItem('dmxx_allowed_pages', JSON.stringify(allowedPages.value))
        localStorage.setItem('dmxx_is_admin', String(isAdmin.value))
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
      isAdmin.value = data.is_admin

      localStorage.setItem('dmxx_token', data.access_token)
      localStorage.setItem('dmxx_profile_name', data.profile_name)
      localStorage.setItem('dmxx_allowed_pages', JSON.stringify(data.allowed_pages))
      localStorage.setItem('dmxx_is_admin', String(data.is_admin))

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
    isAdmin.value = false

    localStorage.removeItem('dmxx_token')
    localStorage.removeItem('dmxx_profile_name')
    localStorage.removeItem('dmxx_allowed_pages')
    localStorage.removeItem('dmxx_is_admin')

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
    isAdmin,
    hasPageAccess,
    checkAuth,
    login,
    logout,
    getAuthHeaders
  }
})

<template>
  <div class="login-container">
    <div class="card login-card">
      <h1 class="login-title">DMXX</h1>
      <p style="text-align: center; color: var(--text-secondary); margin-bottom: 24px;">
        DMX Lighting Controller
      </p>

      <div v-if="error" class="alert alert-error">{{ error }}</div>

      <form @submit.prevent="handleLogin">
        <div class="form-group">
          <label class="form-label">Password</label>
          <input
            type="password"
            class="form-input"
            v-model="password"
            placeholder="Enter password"
            autofocus
          >
        </div>

        <button type="submit" class="btn btn-primary" style="width: 100%;" :disabled="loading">
          {{ loading ? 'Logging in...' : 'Login' }}
        </button>
      </form>

      <!-- Show "Continue as [user]" if IP would auto-authenticate -->
      <div v-if="ipProfileName" style="margin-top: 16px; text-align: center;">
        <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
          Or continue without password:
        </p>
        <button class="btn btn-secondary" style="width: 100%;" @click="continueAsIpUser">
          Continue as {{ ipProfileName }}
        </button>
      </div>

      <p style="text-align: center; margin-top: 16px; font-size: 12px; color: var(--text-secondary);">
        Your IP: {{ clientIp }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const authStore = useAuthStore()

const password = ref('')
const error = ref('')
const loading = ref(false)
const clientIp = ref('')
const ipProfileName = ref('')  // Profile name if IP would auto-authenticate

onMounted(async () => {
  // Router already called checkAuth(), just get the values
  clientIp.value = authStore.clientIp

  if (authStore.authenticated) {
    // Redirect to first allowed page
    const firstPage = authStore.allowedPages[0] || 'faders'
    router.push(`/${firstPage}`)
  } else {
    // Check if IP would auto-authenticate (for "Continue as" button)
    await checkIpProfile()
  }
})

async function checkIpProfile() {
  try {
    // Call status endpoint to see if IP would authenticate
    const response = await fetch('/api/auth/status')
    const data = await response.json()
    if (data.authenticated && data.profile_name) {
      ipProfileName.value = data.profile_name
    }
  } catch (e) {
    // Ignore errors
  }
}

function continueAsIpUser() {
  // Clear logout flag and reload to use IP-based auth
  localStorage.removeItem('dmxx_logged_out')
  window.location.reload()
}

async function handleLogin() {
  error.value = ''
  loading.value = true

  try {
    await authStore.login(password.value)
    // Redirect to first allowed page
    const firstPage = authStore.allowedPages[0] || 'faders'
    router.push(`/${firstPage}`)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

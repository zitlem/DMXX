<template>
  <div class="unauthorized-container">
    <div class="card unauthorized-card">
      <h1 class="unauthorized-title">Access Denied</h1>
      <p class="unauthorized-message">
        You don't have permission to access this page.
      </p>
      <p class="unauthorized-hint">
        Please contact an administrator if you believe this is an error.
      </p>
      <div class="unauthorized-actions">
        <button class="btn btn-primary" @click="goToHome">
          Go to Home
        </button>
        <button class="btn btn-secondary" @click="logout">
          Logout
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const authStore = useAuthStore()

function goToHome() {
  const firstPage = authStore.allowedPages[0] || 'faders'
  router.push(`/${firstPage}`)
}

function logout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.unauthorized-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 20px;
  background: var(--bg-primary);
}

.unauthorized-card {
  max-width: 400px;
  width: 100%;
  padding: 32px;
  text-align: center;
}

.unauthorized-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--error);
  margin-bottom: 16px;
}

.unauthorized-message {
  font-size: 16px;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.unauthorized-hint {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.unauthorized-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}

@media (max-width: 480px) {
  .unauthorized-actions {
    flex-direction: column;
  }
}
</style>

<template>
  <div class="settings-container">
    <h2 class="card-title" style="margin-bottom: 16px;">Settings</h2>

    <!-- Theme Customization -->
    <div class="card" style="margin-bottom: 16px;">
      <div class="card-header">
        <h3 class="card-title">Theme</h3>
      </div>

      <!-- Preset Selection -->
      <div class="form-group">
        <label class="form-label">Preset Theme</label>
        <div class="theme-presets">
          <button
            v-for="(colors, name) in themeStore.presets"
            :key="name"
            class="theme-preset-btn"
            :class="{ active: themeStore.themeData.presetName === name }"
            @click="themeStore.setPreset(name)"
          >
            <div class="theme-preview">
              <div class="preview-swatch" :style="{ background: colors.bgPrimary }"></div>
              <div class="preview-swatch" :style="{ background: colors.accent }"></div>
              <div class="preview-swatch" :style="{ background: colors.textPrimary }"></div>
            </div>
            <span>{{ name.charAt(0).toUpperCase() + name.slice(1) }}</span>
          </button>
        </div>
      </div>

      <!-- Custom Colors -->
      <div class="form-group">
        <label class="form-label">Custom Colors</label>
        <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
          Customize individual colors. Changes are applied immediately.
        </p>

        <div class="color-grid">
          <div class="color-picker-group" v-for="(config, key) in colorConfig" :key="key">
            <label class="color-label">{{ config.label }}</label>
            <div class="color-input-wrapper">
              <input
                type="color"
                :value="themeStore.themeData.colors[key]"
                @input="themeStore.setCustomColor(key, $event.target.value)"
              >
              <input
                type="text"
                class="form-input color-hex"
                :value="themeStore.themeData.colors[key]"
                @change="themeStore.setCustomColor(key, $event.target.value)"
              >
            </div>
          </div>
        </div>

        <div v-if="themeStore.hasUnsavedChanges" class="warning-banner">
          You have unsaved theme changes. Click "Save Custom Theme" to apply to all clients.
        </div>

        <div style="margin-top: 16px; display: flex; gap: 8px;">
          <button class="btn btn-primary" @click="themeStore.saveCustomTheme">
            Save Custom Theme
          </button>
          <button class="btn btn-secondary" @click="themeStore.resetToDefault">
            Reset to Default
          </button>
        </div>
      </div>
    </div>

    <!-- General Settings -->
    <div class="card" style="margin-bottom: 16px;">
      <div class="card-header">
        <h3 class="card-title">General</h3>
      </div>

      <div class="form-group">
        <label class="form-label">Default Transition Type</label>
        <select class="form-select" v-model="settings.default_transition_type" @change="saveSetting('default_transition_type')">
          <option value="instant">Instant</option>
          <option value="fade">Fade</option>
          <option value="crossfade">Crossfade</option>
        </select>
      </div>

      <div class="form-group">
        <label class="form-label">Default Transition Duration (ms)</label>
        <input
          type="number"
          class="form-input"
          v-model.number="settings.default_transition_duration"
          @change="saveSetting('default_transition_duration')"
          min="0"
          step="100"
        >
      </div>

      <div class="form-group">
        <label class="form-label">DMX Refresh Rate (Hz)</label>
        <input
          type="number"
          class="form-input"
          v-model.number="settings.dmx_refresh_rate"
          @change="saveSetting('dmx_refresh_rate')"
          min="1"
          max="44"
          step="1"
        >
        <p style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
          How often DMX data is sent to outputs (1-44 Hz). Higher = smoother fades but more CPU.
        </p>
      </div>

      <div class="form-group">
        <label class="form-label">WebSocket Update Rate (Hz)</label>
        <input
          type="number"
          class="form-input"
          v-model.number="settings.websocket_update_rate"
          @change="saveSetting('websocket_update_rate')"
          min="1"
          max="60"
          step="1"
        >
        <p style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">
          How often UI updates are sent to connected clients (1-60 Hz).
        </p>
      </div>

    </div>

    <!-- Access Profiles (Admin Only) -->
    <div v-if="authStore.isAdmin" class="card" style="margin-bottom: 16px;">
      <div class="card-header">
        <h3 class="card-title">Access Profiles</h3>
        <button class="btn btn-primary" @click="openCreateProfile">Create Profile</button>
      </div>

      <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
        Different passwords grant access to different profiles. Each profile can access only specific pages.
      </p>

      <table class="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Auth</th>
            <th>Allowed Pages</th>
            <th>Allowed Grids</th>
            <th>Allowed Scenes</th>
            <th>Admin</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="profile in profiles" :key="profile.id">
            <td>{{ profile.name }}</td>
            <td>
              <span class="auth-badges">
                <span v-if="profile.has_password" class="auth-badge">Password</span>
                <span v-if="profile.ip_addresses && profile.ip_addresses.length" class="auth-badge ip-badge">
                  {{ profile.ip_addresses.length }} IP{{ profile.ip_addresses.length > 1 ? 's' : '' }}
                </span>
              </span>
            </td>
            <td>
              <span class="page-badges">
                <span v-for="page in profile.allowed_pages" :key="page" class="page-badge">
                  {{ pageLabels[page] || page }}
                </span>
              </span>
            </td>
            <td>
              <span class="page-badges">
                <span v-if="!profile.allowed_grids || profile.allowed_grids.length === 0" class="page-badge" style="opacity: 0.6;">
                  All
                </span>
                <span v-else v-for="gridId in profile.allowed_grids" :key="gridId" class="page-badge">
                  {{ getGridName(gridId) }}
                </span>
              </span>
            </td>
            <td>
              <span class="page-badges">
                <span v-if="!profile.allowed_scenes || profile.allowed_scenes.length === 0" class="page-badge" style="opacity: 0.6;">
                  All
                </span>
                <span v-else v-for="sceneId in profile.allowed_scenes" :key="sceneId" class="page-badge">
                  {{ getSceneName(sceneId) }}
                </span>
              </span>
            </td>
            <td>{{ profile.is_admin ? 'Yes' : 'No' }}</td>
            <td>
              <button class="btn btn-small btn-secondary" @click="editProfile(profile)">Edit</button>
              <button class="btn btn-small btn-danger" @click="confirmDeleteProfile(profile)" :disabled="profile.name === authStore.profileName">Delete</button>
            </td>
          </tr>
          <tr v-if="profiles.length === 0">
            <td colspan="7" style="text-align: center; color: var(--text-secondary);">
              No profiles yet
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Backup & Restore -->
    <div class="card" style="margin-bottom: 16px;">
      <div class="card-header">
        <h3 class="card-title">Backup & Restore</h3>
        <button class="btn btn-primary" @click="showCreateBackup = true">Create Backup</button>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Comment</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="backup in backups" :key="backup.id">
            <td>{{ formatDate(backup.timestamp) }}</td>
            <td>{{ backup.comment || '-' }}</td>
            <td>
              <button class="btn btn-small btn-secondary" @click="confirmRestore(backup)">Restore</button>
              <button class="btn btn-small btn-danger" @click="confirmDeleteBackup(backup)">Delete</button>
            </td>
          </tr>
          <tr v-if="backups.length === 0">
            <td colspan="3" style="text-align: center; color: var(--text-secondary);">
              No backups yet
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Danger Zone -->
    <div class="card" style="border-color: var(--error);">
      <div class="card-header">
        <h3 class="card-title" style="color: var(--error);">Danger Zone</h3>
      </div>
      <button class="btn btn-danger" @click="confirmResetSettings">Reset Everything</button>
    </div>

    <!-- Create Backup Modal -->
    <div v-if="showCreateBackup" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Create Backup</h3>
          <button class="modal-close" @click="showCreateBackup = false">&times;</button>
        </div>
        <div class="form-group">
          <label class="form-label">Comment (optional)</label>
          <input type="text" class="form-input" v-model="backupComment" placeholder="e.g., Before show update">
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showCreateBackup = false">Cancel</button>
          <button class="btn btn-primary" @click="createBackup">Create</button>
        </div>
      </div>
    </div>

    <!-- Restore Confirmation -->
    <div v-if="restoringBackup" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Restore Backup</h3>
          <button class="modal-close" @click="restoringBackup = null">&times;</button>
        </div>
        <p>Are you sure you want to restore from this backup?</p>
        <p style="color: var(--text-secondary);">{{ formatDate(restoringBackup.timestamp) }}</p>
        <p style="color: var(--warning); margin-top: 8px;">This will overwrite current data. The application will need to restart.</p>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="restoringBackup = null">Cancel</button>
          <button class="btn btn-danger" @click="restoreBackup">Restore</button>
        </div>
      </div>
    </div>

    <!-- Delete Backup Confirmation -->
    <div v-if="deletingBackup" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Delete Backup</h3>
          <button class="modal-close" @click="deletingBackup = null">&times;</button>
        </div>
        <p>Are you sure you want to delete this backup?</p>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="deletingBackup = null">Cancel</button>
          <button class="btn btn-danger" @click="deleteBackup">Delete</button>
        </div>
      </div>
    </div>

    <!-- Create/Edit Profile Modal -->
    <div v-if="showProfileModal" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingProfile ? 'Edit Profile' : 'Create Profile' }}</h3>
          <button class="modal-close" @click="closeProfileModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Profile Name</label>
          <input type="text" class="form-input" v-model="profileForm.name" placeholder="e.g., Operator">
        </div>

        <div class="form-group">
          <label class="form-label">Password (optional if using IP)</label>
          <input type="password" class="form-input" v-model="profileForm.password" :placeholder="editingProfile ? 'Leave blank to keep current' : 'Enter password'">
        </div>

        <div class="form-group">
          <label class="form-label">IP Addresses (optional if using password)</label>
          <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
            Users from these IPs will automatically use this profile. Use * for wildcards (e.g., 192.168.1.*). Exact IPs are matched before wildcards, so you can use 10.1.10.* for users and 10.1.10.102 for admin.
          </p>
          <div v-for="(ip, index) in profileForm.ip_addresses" :key="index" class="ip-row">
            <input type="text" class="form-input" v-model="profileForm.ip_addresses[index]" placeholder="e.g., 192.168.1.100">
            <button class="btn btn-small btn-danger" @click="removeIpFromProfile(index)">Remove</button>
          </div>
          <button class="btn btn-small btn-secondary" @click="addIpToProfile" style="margin-top: 8px;">Add IP</button>
        </div>

        <div class="form-group">
          <label class="form-label">Allowed Pages</label>
          <div class="page-checkboxes">
            <label v-for="page in availablePages" :key="page.id" class="page-checkbox-label">
              <input type="checkbox" :value="page.id" v-model="profileForm.allowed_pages">
              {{ page.name }}
            </label>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Allowed Grids</label>
          <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
            Select which grids this profile can access on the Groups page. Leave empty for all grids.
          </p>
          <div class="page-checkboxes" v-if="availableGrids.length > 0">
            <label v-for="grid in availableGrids" :key="grid.id" class="page-checkbox-label">
              <input type="checkbox" :value="grid.id" v-model="profileForm.allowed_grids">
              {{ grid.name }}
            </label>
          </div>
          <div v-else style="color: var(--text-secondary); font-size: 13px; font-style: italic;">
            No grids created yet. Create grids on the Groups page first.
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Allowed Scenes</label>
          <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">
            Select which scenes this profile can access in the scene bar and Scenes page. Leave empty for all scenes.
          </p>
          <div class="page-checkboxes" v-if="availableScenes.length > 0">
            <label v-for="scene in availableScenes" :key="scene.id" class="page-checkbox-label">
              <input type="checkbox" :value="scene.id" v-model="profileForm.allowed_scenes">
              {{ scene.name }}
            </label>
          </div>
          <div v-else style="color: var(--text-secondary); font-size: 13px; font-style: italic;">
            No scenes created yet. Create scenes on the Scenes page first.
          </div>
        </div>

        <div class="form-group">
          <label class="page-checkbox-label">
            <input type="checkbox" v-model="profileForm.is_admin">
            Admin (can manage profiles and access all settings)
          </label>
        </div>

        <div class="form-group">
          <label style="font-weight: 500; margin-bottom: 8px; display: block;">Feature Permissions</label>
          <label class="page-checkbox-label">
            <input type="checkbox" v-model="profileForm.can_park">
            Can Park Channels (lock channels at fixed values)
          </label>
          <label class="page-checkbox-label">
            <input type="checkbox" v-model="profileForm.can_highlight">
            Can Highlight Channels (solo/highlight mode)
          </label>
          <label class="page-checkbox-label">
            <input type="checkbox" v-model="profileForm.can_bypass">
            Can Toggle Input Bypass (temporarily disable DMX input)
          </label>
        </div>

        <div v-if="profileError" class="alert alert-error">{{ profileError }}</div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeProfileModal">Cancel</button>
          <button class="btn btn-primary" @click="saveProfile" :disabled="!canSaveProfile">
            {{ editingProfile ? 'Update' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useThemeStore } from '../stores/theme.js'
import { PAGES } from '../config/pages.js'

const authStore = useAuthStore()
const themeStore = useThemeStore()

const colorConfig = {
  bgPrimary: { label: 'Background Primary' },
  bgSecondary: { label: 'Background Secondary' },
  bgTertiary: { label: 'Background Tertiary' },
  textPrimary: { label: 'Text Primary' },
  textSecondary: { label: 'Text Secondary' },
  accent: { label: 'Accent' },
  accentHover: { label: 'Accent Hover' },
  success: { label: 'Success' },
  warning: { label: 'Warning' },
  error: { label: 'Error' },
  border: { label: 'Border' },
  faderBg: { label: 'Fader Background' },
  faderFill: { label: 'Fader Fill' },
  indicatorRemote: { label: 'Remote Indicator' },
  indicatorLocal: { label: 'Local Indicator' },
  indicatorGroup: { label: 'Group Indicator' }
}

const settings = ref({
  default_transition_type: 'instant',
  default_transition_duration: 0,
  dmx_refresh_rate: 40,
  websocket_update_rate: 30
})

const backups = ref([])
const showCreateBackup = ref(false)
const backupComment = ref('')
const restoringBackup = ref(null)
const deletingBackup = ref(null)

// Profile management state
const profiles = ref([])
const showProfileModal = ref(false)
const editingProfile = ref(null)
const profileForm = ref({
  name: '',
  password: '',
  ip_addresses: [],
  allowed_pages: [],
  allowed_grids: [],
  allowed_scenes: [],
  is_admin: false,
  can_park: true,
  can_highlight: true,
  can_bypass: true
})
const profileError = ref('')

// Available grids and scenes for profile access control
const availableGrids = ref([])
const availableScenes = ref([])

// Pages list from single source of truth
const availablePages = PAGES
const pageLabels = Object.fromEntries(PAGES.map(p => [p.id, p.name]))

// Helper to get grid name by ID
function getGridName(gridId) {
  const grid = availableGrids.value.find(g => g.id === gridId)
  return grid ? grid.name : `Grid ${gridId}`
}

// Helper to get scene name by ID
function getSceneName(sceneId) {
  const scene = availableScenes.value.find(s => s.id === sceneId)
  return scene ? scene.name : `Scene ${sceneId}`
}

// Computed for profile save button
const canSaveProfile = computed(() => {
  if (!profileForm.value.name) return false
  if (profileForm.value.allowed_pages.length === 0) return false
  // Must have password or IP addresses (for new profiles)
  // For editing, existing password is kept if blank
  const hasPassword = profileForm.value.password || (editingProfile.value && editingProfile.value.has_password)
  const hasIps = profileForm.value.ip_addresses.filter(ip => ip.trim()).length > 0
  if (!editingProfile.value && !hasPassword && !hasIps) return false
  return true
})

onMounted(async () => {
  await loadSettings()
  await loadBackups()
  await loadProfiles()
  await loadGrids()
  await loadScenes()
})

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

async function loadSettings() {
  try {
    const response = await fetchWithAuth('/api/settings')
    const data = await response.json()
    settings.value = data.settings
  } catch (e) {
    console.error('Failed to load settings:', e)
  }
}

async function saveSetting(key) {
  try {
    await fetchWithAuth('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value: String(settings.value[key]) })
    })
  } catch (e) {
    console.error('Failed to save setting:', e)
  }
}

async function loadBackups() {
  try {
    const response = await fetchWithAuth('/api/backup/list')
    const data = await response.json()
    backups.value = data.backups
  } catch (e) {
    console.error('Failed to load backups:', e)
  }
}

async function createBackup() {
  try {
    await fetchWithAuth('/api/backup/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment: backupComment.value })
    })
    await loadBackups()
    showCreateBackup.value = false
    backupComment.value = ''
  } catch (e) {
    console.error('Failed to create backup:', e)
  }
}

function confirmRestore(backup) {
  restoringBackup.value = backup
}

async function restoreBackup() {
  try {
    await fetchWithAuth(`/api/backup/restore/${restoringBackup.value.id}`, {
      method: 'POST'
    })
    alert('Backup restored. Please restart the application.')
  } catch (e) {
    console.error('Failed to restore backup:', e)
  }
  restoringBackup.value = null
}

function confirmDeleteBackup(backup) {
  deletingBackup.value = backup
}

async function deleteBackup() {
  try {
    await fetchWithAuth(`/api/backup/${deletingBackup.value.id}`, {
      method: 'DELETE'
    })
    await loadBackups()
  } catch (e) {
    console.error('Failed to delete backup:', e)
  }
  deletingBackup.value = null
}

async function confirmResetSettings() {
  if (confirm('WARNING: This will delete ALL data including universes, fixtures, scenes, patches, profiles, and API tokens. Only backups will be preserved.\n\nAre you sure you want to reset everything?')) {
    try {
      await fetchWithAuth('/api/settings/reset', { method: 'POST' })
      await loadSettings()
      await loadProfiles()
    } catch (e) {
      console.error('Failed to reset settings:', e)
    }
  }
}

function formatDate(isoString) {
  return new Date(isoString).toLocaleString()
}

// Profile management functions
async function loadProfiles() {
  if (!authStore.isAdmin) return
  try {
    const response = await fetchWithAuth('/api/auth/profiles')
    if (response.ok) {
      profiles.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load profiles:', e)
  }
}

async function loadGrids() {
  try {
    const response = await fetchWithAuth('/api/groups/grids')
    if (response.ok) {
      const data = await response.json()
      availableGrids.value = data.grids || []
    }
  } catch (e) {
    console.error('Failed to load grids:', e)
  }
}

async function loadScenes() {
  try {
    const response = await fetchWithAuth('/api/scenes')
    if (response.ok) {
      const data = await response.json()
      availableScenes.value = data.scenes || []
    }
  } catch (e) {
    console.error('Failed to load scenes:', e)
  }
}

function openCreateProfile() {
  editingProfile.value = null
  profileForm.value = {
    name: '',
    password: '',
    ip_addresses: [],
    allowed_pages: [],
    allowed_grids: [],
    allowed_scenes: [],
    is_admin: false,
    can_park: true,
    can_highlight: true,
    can_bypass: true
  }
  profileError.value = ''
  showProfileModal.value = true
}

function editProfile(profile) {
  editingProfile.value = profile
  profileForm.value = {
    name: profile.name,
    password: '',
    ip_addresses: profile.ip_addresses ? [...profile.ip_addresses] : [],
    allowed_pages: [...profile.allowed_pages],
    allowed_grids: profile.allowed_grids ? [...profile.allowed_grids] : [],
    allowed_scenes: profile.allowed_scenes ? [...profile.allowed_scenes] : [],
    is_admin: profile.is_admin,
    can_park: profile.can_park !== false,
    can_highlight: profile.can_highlight !== false,
    can_bypass: profile.can_bypass !== false
  }
  profileError.value = ''
  showProfileModal.value = true
}

function addIpToProfile() {
  profileForm.value.ip_addresses.push('')
}

function removeIpFromProfile(index) {
  profileForm.value.ip_addresses.splice(index, 1)
}

async function saveProfile() {
  profileError.value = ''

  // Validation
  if (!profileForm.value.name.trim()) {
    profileError.value = 'Profile name is required'
    return
  }
  if (profileForm.value.allowed_pages.length === 0) {
    profileError.value = 'Select at least one page'
    return
  }

  // Filter out empty IP addresses
  const validIps = profileForm.value.ip_addresses.filter(ip => ip.trim())

  // Must have password or IPs for new profiles
  const hasPassword = profileForm.value.password || (editingProfile.value && editingProfile.value.has_password)
  if (!editingProfile.value && !profileForm.value.password && validIps.length === 0) {
    profileError.value = 'Profile must have either a password or IP addresses'
    return
  }

  try {
    const payload = {
      name: profileForm.value.name.trim(),
      allowed_pages: profileForm.value.allowed_pages,
      allowed_grids: profileForm.value.allowed_grids,
      allowed_scenes: profileForm.value.allowed_scenes,
      is_admin: profileForm.value.is_admin,
      can_park: profileForm.value.can_park,
      can_highlight: profileForm.value.can_highlight,
      can_bypass: profileForm.value.can_bypass
    }

    // Only include password if provided
    if (profileForm.value.password) {
      payload.password = profileForm.value.password
    }

    // Include IP addresses
    payload.ip_addresses = validIps.length > 0 ? validIps : null

    let response
    if (editingProfile.value) {
      response = await fetchWithAuth(`/api/auth/profiles/${editingProfile.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
    } else {
      response = await fetchWithAuth('/api/auth/profiles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
    }

    if (response.ok) {
      await loadProfiles()
      closeProfileModal()
    } else {
      const error = await response.json()
      profileError.value = error.detail || 'Failed to save profile'
    }
  } catch (e) {
    console.error('Failed to save profile:', e)
    profileError.value = 'Failed to save profile'
  }
}

function closeProfileModal() {
  showProfileModal.value = false
  editingProfile.value = null
  profileForm.value = {
    name: '',
    password: '',
    ip_addresses: [],
    allowed_pages: [],
    allowed_grids: [],
    allowed_scenes: [],
    is_admin: false,
    can_park: true,
    can_highlight: true,
    can_bypass: true
  }
  profileError.value = ''
}

async function confirmDeleteProfile(profile) {
  if (!confirm(`Are you sure you want to delete the "${profile.name}" profile?`)) {
    return
  }

  try {
    const response = await fetchWithAuth(`/api/auth/profiles/${profile.id}`, {
      method: 'DELETE'
    })

    if (response.ok) {
      await loadProfiles()
    } else {
      const error = await response.json()
      alert(error.detail || 'Failed to delete profile')
    }
  } catch (e) {
    console.error('Failed to delete profile:', e)
    alert('Failed to delete profile')
  }
}

</script>

<style scoped>
.settings-container {
  max-width: 800px;
  margin: 0 auto;
}

/* Theme preset buttons */
.theme-presets {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.theme-preset-btn {
  padding: 12px;
  background: var(--bg-tertiary);
  border: 2px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
  transition: all 0.2s;
}

.theme-preset-btn:hover {
  border-color: var(--accent);
}

.theme-preset-btn.active {
  border-color: var(--accent);
  background: rgba(233, 69, 96, 0.1);
}

.theme-preview {
  display: flex;
  gap: 4px;
}

.preview-swatch {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

/* Color picker grid */
.color-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
}

.color-picker-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.color-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.color-input-wrapper {
  display: flex;
  gap: 8px;
  align-items: center;
}

.color-input-wrapper input[type="color"] {
  width: 40px;
  height: 32px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  padding: 0;
  background: transparent;
}

.color-input-wrapper input[type="color"]::-webkit-color-swatch-wrapper {
  padding: 0;
}

.color-input-wrapper input[type="color"]::-webkit-color-swatch {
  border: 1px solid var(--border);
  border-radius: 4px;
}

.color-hex {
  width: 100px;
  font-family: monospace;
}

@media (max-width: 768px) {
  .color-grid {
    grid-template-columns: 1fr;
  }

  /* Access Profiles table: hide Allowed Grids (4th) and Admin (5th) columns */
  .data-table th:nth-child(4),
  .data-table td:nth-child(4),
  .data-table th:nth-child(5),
  .data-table td:nth-child(5) {
    display: none;
  }

  .data-table .btn {
    padding: 4px 8px;
    font-size: 11px;
  }

  .page-badge {
    font-size: 9px;
    padding: 2px 4px;
  }

  .auth-badge {
    font-size: 9px;
    padding: 2px 4px;
  }
}

/* Page badges for profile table */
.page-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.page-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}

/* Page checkboxes for profile modal */
.page-checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.page-checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 14px;
}

.page-checkbox-label input[type="checkbox"] {
  accent-color: var(--accent);
  width: 16px;
  height: 16px;
}

/* Auth badges for profile table */
.auth-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.auth-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  color: var(--text-secondary);
}

.auth-badge.ip-badge {
  background: rgba(59, 130, 246, 0.2);
  border-color: rgba(59, 130, 246, 0.5);
  color: #93c5fd;
}

/* IP address rows in profile modal */
.ip-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.ip-row .form-input {
  flex: 1;
}

/* Warning banner for unsaved changes */
.warning-banner {
  background: var(--warning);
  color: #1a1a2e;
  padding: 12px 16px;
  border-radius: 6px;
  margin-top: 16px;
  font-weight: 500;
}

</style>

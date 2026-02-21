<template>
  <div class="app-layout" v-if="authenticated">
    <!-- Main content -->
    <div class="main-content">
      <nav class="navbar">
        <button class="menu-toggle" @click="mobileMenuOpen = !mobileMenuOpen">&#9776;</button>
        <div class="nav-brand">DMXX</div>
        <div v-if="mobileMenuOpen" class="menu-overlay" @click="mobileMenuOpen = false"></div>
        <div class="nav-links" :class="{ open: mobileMenuOpen }">
          <router-link v-if="authStore.hasPageAccess('faders')" to="/faders" class="nav-link" @click="mobileMenuOpen = false">Faders</router-link>
          <router-link v-if="authStore.hasPageAccess('groups')" to="/groups" class="nav-link" @click="mobileMenuOpen = false">Groups</router-link>
          <router-link v-if="authStore.hasPageAccess('scenes')" to="/scenes" class="nav-link" @click="mobileMenuOpen = false">Scenes</router-link>
          <router-link v-if="authStore.hasPageAccess('fixtures')" to="/fixtures" class="nav-link" @click="mobileMenuOpen = false">Fixtures</router-link>
          <router-link v-if="authStore.hasPageAccess('patch')" to="/patch" class="nav-link" @click="mobileMenuOpen = false">Patch</router-link>
          <router-link v-if="authStore.hasPageAccess('io')" to="/io" class="nav-link" @click="mobileMenuOpen = false">I/O</router-link>
          <router-link v-if="authStore.hasPageAccess('midi')" to="/midi" class="nav-link" @click="mobileMenuOpen = false">MIDI</router-link>
          <router-link v-if="authStore.hasPageAccess('io')" to="/mapping" class="nav-link" @click="mobileMenuOpen = false">Mapping</router-link>
          <router-link v-if="authStore.hasPageAccess('settings')" to="/settings" class="nav-link" @click="mobileMenuOpen = false">Settings</router-link>
          <router-link v-if="authStore.hasPageAccess('settings')" to="/remote-api" class="nav-link" @click="mobileMenuOpen = false">Remote API</router-link>
          <router-link v-if="authStore.hasPageAccess('io')" to="/monitor" class="nav-link" @click="mobileMenuOpen = false">Monitor</router-link>
          <router-link v-if="authStore.hasPageAccess('io')" to="/control-flow" class="nav-link" @click="mobileMenuOpen = false">Control Flow</router-link>
          <router-link to="/help" class="nav-link" @click="mobileMenuOpen = false">Help</router-link>
          <button class="btn btn-small btn-secondary nav-logout" @click="logout">Logout</button>
        </div>

        <div class="nav-right">
          <span class="profile-name">{{ authStore.profileName }}</span>
          <div :class="['connection-status', { connected: wsConnected }]">
            <span class="status-dot"></span>
            <span class="status-text">{{ wsConnected ? 'Connected' : 'Disconnected' }}</span>
          </div>
          <button class="btn btn-small btn-secondary desktop-logout" @click="logout">Logout</button>
        </div>
      </nav>

      <main class="page-content">
        <router-view />
      </main>

      <!-- Bottom Scene Bar -->
      <div class="scene-bar">
        <button
          class="scene-btn blackout-btn"
          :class="{ active: dmxStore.blackoutActive }"
          @click="toggleBlackout"
        >
          BLACKOUT
        </button>
        <div class="scene-buttons">
          <button
            v-for="scene in limitedScenes"
            :key="scene.id"
            class="scene-btn"
            :class="{ active: dmxStore.activeScene === scene.id }"
            @click="recallScene(scene)"
          >
            {{ scene.name }}
          </button>
        </div>
        <button class="scene-btn add-btn" @click="openSaveSceneModal">+</button>
      </div>
    </div>

    <!-- Save Scene Modal -->
    <div v-if="showSaveScene" class="modal-overlay" @click.self="showSaveScene = false">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">Save Scene</h3>
          <button class="modal-close" @click="showSaveScene = false">&times;</button>
        </div>
        <div class="form-group">
          <label class="form-label">Scene Name</label>
          <input type="text" class="form-input" v-model="newSceneName" placeholder="Enter scene name">
        </div>
        <div class="form-group">
          <label class="form-label">Transition Type</label>
          <select class="form-select" v-model="newSceneTransition">
            <option value="instant">Instant</option>
            <option value="fade">Fade</option>
            <option value="crossfade">Crossfade</option>
          </select>
        </div>
        <div class="form-group" v-if="newSceneTransition !== 'instant'">
          <label class="form-label">Duration (ms)</label>
          <input type="number" class="form-input" v-model.number="newSceneDuration" min="0" step="100">
        </div>
        <div class="form-group">
          <label class="form-label">Universes to Capture</label>
          <div class="universe-select-header">
            <button class="btn btn-small btn-secondary" @click="selectedUniverses = universes.map(u => u.id)">All</button>
            <button class="btn btn-small btn-secondary" @click="selectedUniverses = []">None</button>
            <button class="btn btn-small btn-secondary" @click="showJumpPopup = true" v-if="universes.length > 4">Jump</button>
          </div>
          <div class="universe-checkboxes">
            <label
              v-for="u in universes"
              :key="u.id"
              :data-universe-id="u.id"
              class="universe-checkbox"
              :class="{ selected: selectedUniverses.includes(u.id) }"
            >
              <input
                type="checkbox"
                :checked="selectedUniverses.includes(u.id)"
                @change="toggleUniverse(u.id)"
              >
              <span class="checkbox-label">{{ u.label }}</span>
            </label>
          </div>
          <p v-if="selectedUniverses.length === 0" class="warning-text">
            Please select at least one universe
          </p>
        </div>
        <div v-if="enabledGroups.length > 0" class="form-group">
          <label class="form-label">Group Faders to Capture</label>
          <div class="universe-select-header">
            <button class="btn btn-small btn-secondary" @click="selectedGroups = enabledGroups.map(g => g.id)">All</button>
            <button class="btn btn-small btn-secondary" @click="selectedGroups = []">None</button>
          </div>
          <div class="universe-checkboxes">
            <label
              v-for="g in enabledGroups"
              :key="g.id"
              class="universe-checkbox group-checkbox"
              :class="{ selected: selectedGroups.includes(g.id) }"
            >
              <input
                type="checkbox"
                :checked="selectedGroups.includes(g.id)"
                @change="toggleGroup(g.id)"
              >
              <span class="checkbox-label">{{ g.name }}</span>
            </label>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showSaveScene = false">Cancel</button>
          <button class="btn btn-primary" @click="saveScene" :disabled="!canSaveBottomBarScene">Save</button>
        </div>
      </div>
    </div>

    <!-- Jump Popup -->
    <div v-if="showJumpPopup" class="modal-overlay" @click.self="showJumpPopup = false">
      <div class="jump-popup">
        <div class="jump-popup-header">
          <h4>Select Universe</h4>
          <button class="modal-close" @click="showJumpPopup = false">&times;</button>
        </div>
        <div class="jump-popup-list">
          <button
            v-for="u in universes"
            :key="u.id"
            class="jump-popup-item"
            :class="{ selected: selectedUniverses.includes(u.id) }"
            @click="jumpToUniverse(u.id)"
          >
            {{ u.label }}
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- Login page -->
  <router-view v-else />
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useAuthStore } from './stores/auth.js'
import { useDmxStore } from './stores/dmx.js'
import { useThemeStore } from './stores/theme.js'
import { wsManager } from './websocket.js'

const router = useRouter()
const authStore = useAuthStore()
const dmxStore = useDmxStore()
const themeStore = useThemeStore()

// Load cached theme immediately on component setup
themeStore.loadCachedTheme()

// Use storeToRefs to get reactive refs from Pinia store
const { authenticated } = storeToRefs(authStore)

const wsConnected = ref(false)
const showSaveScene = ref(false)
const newSceneName = ref('')
const newSceneTransition = ref('instant')
const newSceneDuration = ref(0)
let checkConnectionInterval = null

// Universe selection for save scene modal
const universes = ref([])
const selectedUniverses = ref([])
const showJumpPopup = ref(false)

// Group selection for save scene modal
const groups = ref([])
const selectedGroups = ref([])

// Mobile menu
const mobileMenuOpen = ref(false)

// Close mobile menu on route change
watch(() => router.currentRoute.value, () => {
  mobileMenuOpen.value = false
})

// Limit scenes shown in bottom bar to 10, filtered by allowed scenes
const limitedScenes = computed(() => {
  return dmxStore.scenes
    .filter(scene => authStore.hasSceneAccess(scene.id))
    .slice(0, 10)
})

// Computed for enabled groups
const enabledGroups = computed(() => {
  if (!groups.value || !Array.isArray(groups.value)) return []
  return groups.value.filter(g => g.enabled)
})

// Computed for save button disabled state
const canSaveBottomBarScene = computed(() => {
  if (!newSceneName.value) return false
  if (selectedUniverses.value.length === 0) return false
  return true
})

// Watch for auth changes and setup websocket
watch(authenticated, (isAuth) => {
  if (isAuth) {
    setupAuthenticatedState()
  }
}, { immediate: true })

async function setupAuthenticatedState() {
  // Connect WebSocket
  wsManager.connect()
  wsConnected.value = wsManager.connected.value

  // Listen for active scene changes from other clients
  wsManager.on('active_scene_changed', handleActiveSceneChanged)
  // Listen for blackout changes from other clients
  wsManager.on('blackout', handleBlackoutChange)
  // Listen for scene list changes from other clients
  wsManager.on('scenes_changed', handleScenesChanged)
  // Listen for patch changes from other clients
  wsManager.on('patches_changed', handlePatchesChanged)
  // Listen for fixture changes from other clients
  wsManager.on('fixtures_changed', handleFixturesChanged)

  // Watch connection status
  if (checkConnectionInterval) clearInterval(checkConnectionInterval)
  checkConnectionInterval = setInterval(() => {
    wsConnected.value = wsManager.connected.value
  }, 1000)

  // Load initial data including theme
  await Promise.all([
    dmxStore.loadUniverses(),
    dmxStore.loadScenes(),
    dmxStore.checkBlackoutStatus(),
    dmxStore.loadGrandmasters(),
    themeStore.loadTheme(),
    themeStore.loadPresets()
  ])

  // Initialize universes for save scene modal
  universes.value = dmxStore.universes
  selectedUniverses.value = universes.value.map(u => u.id)
}

function handleActiveSceneChanged(data) {
  dmxStore.activeScene = data.scene_id
  // Start/extend grace period when receiving scene change broadcast
  // This protects ALL clients, not just the one that initiated recall
  // Use 5 seconds to cover fade transitions (exact duration not in broadcast)
  if (data.scene_id !== null) {
    dmxStore.startSceneRecallGracePeriod(5000)
  }
}

function handleBlackoutChange(data) {
  dmxStore.blackoutActive = data.active
}

function handleScenesChanged() {
  dmxStore.loadScenes()
}

function handlePatchesChanged() {
  dmxStore.loadPatches()
  dmxStore.reloadAllChannelLabels()
}

function handleFixturesChanged() {
  dmxStore.loadFixtures()
}

function jumpToUniverse(universeId) {
  // Scroll to the universe checkbox
  const checkboxEl = document.querySelector(`.universe-checkbox[data-universe-id="${universeId}"]`)
  if (checkboxEl) {
    checkboxEl.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }
  showJumpPopup.value = false
}

onMounted(async () => {
  await authStore.checkAuth()
})

onUnmounted(() => {
  if (checkConnectionInterval) clearInterval(checkConnectionInterval)
  wsManager.off('active_scene_changed', handleActiveSceneChanged)
  wsManager.off('blackout', handleBlackoutChange)
  wsManager.off('scenes_changed', handleScenesChanged)
  wsManager.off('patches_changed', handlePatchesChanged)
  wsManager.off('fixtures_changed', handleFixturesChanged)
  wsManager.disconnect()
})

async function toggleBlackout() {
  await dmxStore.toggleBlackout()
}

async function recallScene(scene) {
  // Grace period includes scene duration for fade/crossfade transitions
  dmxStore.startSceneRecallGracePeriod(scene.duration || 0)
  wsManager.setActiveScene(scene.id)
  await dmxStore.recallScene(scene.id)
}

async function getDefaultTransitionSettings() {
  try {
    const response = await fetch('/api/settings', {
      headers: authStore.getAuthHeaders()
    })
    const data = await response.json()
    return {
      type: data.settings?.default_transition_type || 'instant',
      duration: parseInt(data.settings?.default_transition_duration) || 0
    }
  } catch (e) {
    console.error('Failed to load default transition settings:', e)
    return { type: 'instant', duration: 0 }
  }
}

async function loadGroups() {
  try {
    const response = await fetch('/api/groups', { headers: authStore.getAuthHeaders() })
    if (response.ok) {
      const data = await response.json()
      groups.value = data.groups || []
    }
  } catch (e) {
    console.error('Failed to load groups:', e)
    groups.value = []
  }
}

async function openSaveSceneModal() {
  const defaults = await getDefaultTransitionSettings()
  newSceneTransition.value = defaults.type
  newSceneDuration.value = defaults.duration
  await loadGroups()
  selectedGroups.value = enabledGroups.value.map(g => g.id)
  showSaveScene.value = true
}

async function saveScene() {
  if (!newSceneName.value) return

  const universeFilter = selectedUniverses.value.length === universes.value.length
    ? null
    : selectedUniverses.value

  const groupFilter = selectedGroups.value.length === enabledGroups.value.length
    ? null
    : selectedGroups.value

  await dmxStore.createScene(
    newSceneName.value,
    newSceneTransition.value,
    newSceneTransition.value === 'instant' ? 0 : newSceneDuration.value,
    universeFilter,
    groupFilter
  )

  newSceneName.value = ''
  newSceneTransition.value = 'instant'
  newSceneDuration.value = 0
  selectedUniverses.value = universes.value.map(u => u.id)
  selectedGroups.value = enabledGroups.value.map(g => g.id)
  showSaveScene.value = false
}

function toggleUniverse(universeId) {
  const idx = selectedUniverses.value.indexOf(universeId)
  if (idx === -1) {
    selectedUniverses.value.push(universeId)
  } else {
    selectedUniverses.value.splice(idx, 1)
  }
}

function toggleGroup(groupId) {
  const idx = selectedGroups.value.indexOf(groupId)
  if (idx === -1) {
    selectedGroups.value.push(groupId)
  } else {
    selectedGroups.value.splice(idx, 1)
  }
}

function logout() {
  authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.menu-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 999;
}

.profile-name {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.connection-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--error);
}

.connection-status.connected .status-dot {
  background: var(--success);
}

/* Universe selection styles */
.universe-select-header {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.universe-checkboxes {
  display: flex;
  flex-wrap: nowrap;
  gap: 8px;
  overflow-x: auto;
  max-width: 100%;
  padding-bottom: 8px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.universe-checkboxes::-webkit-scrollbar {
  height: 6px;
}

.universe-checkboxes::-webkit-scrollbar-track {
  background: transparent;
}

.universe-checkboxes::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 3px;
}

.universe-checkbox {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  white-space: nowrap;
}

.universe-checkbox:hover {
  border-color: var(--accent);
}

.universe-checkbox.selected {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  border-color: var(--accent);
}

.universe-checkbox input[type="checkbox"] {
  accent-color: var(--accent);
}

.checkbox-label {
  font-size: 13px;
}

.warning-text {
  color: #f59e0b;
  font-size: 12px;
  margin-top: 8px;
}

/* Group checkbox styling */
.group-checkbox {
  background: rgba(74, 222, 128, 0.1) !important;
  border-color: rgba(74, 222, 128, 0.3) !important;
}

.group-checkbox.selected {
  background: rgba(74, 222, 128, 0.2) !important;
  border-color: var(--indicator-group, #4ade80) !important;
}

.group-checkbox:hover {
  border-color: var(--indicator-group, #4ade80) !important;
}

/* Jump popup styles */
.jump-popup {
  background: var(--bg-secondary);
  border-radius: 12px;
  border: 1px solid var(--border);
  min-width: 300px;
  max-width: 400px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
}

.jump-popup-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.jump-popup-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.jump-popup-list {
  padding: 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.jump-popup-item {
  padding: 10px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: white;
  cursor: pointer;
  text-align: left;
  font-size: 14px;
  transition: all 0.15s;
}

.jump-popup-item:hover {
  border-color: var(--accent);
  background: rgba(233, 69, 96, 0.1);
}

.jump-popup-item.selected {
  background: rgba(233, 69, 96, 0.2);
  border-color: var(--accent);
}
</style>

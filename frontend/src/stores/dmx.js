import { defineStore } from 'pinia'
import { ref, reactive } from 'vue'
import { wsManager } from '../websocket.js'
import { useAuthStore } from './auth.js'

export const useDmxStore = defineStore('dmx', () => {
  const universes = ref([])
  const fixtures = ref([])
  const patches = ref([])
  const scenes = ref([])
  const currentUniverse = ref(1)
  const blackoutActive = ref(false)
  const channelLabels = reactive({})
  const activeScene = ref(null)

  // Scene recall grace period - prevents race conditions when recalling scenes
  const sceneRecallInProgress = ref(false)
  let sceneRecallTimeout = null

  // Input display and source tracking for fader status indicators
  const inputDisplayValues = reactive({})  // { universeId: [512 values] }
  const inputDisplayMode = reactive({})    // { universeId: boolean }
  const channelSources = reactive({})      // { universeId: { channel: "local"|"input"|"user_xxx" } }
  const myClientId = ref(null)             // This client's ID from WebSocket connection

  async function fetchWithAuth(url, options = {}) {
    const authStore = useAuthStore()
    options.headers = {
      ...options.headers,
      ...authStore.getAuthHeaders()
    }
    return fetch(url, options)
  }

  async function loadUniverses() {
    try {
      const response = await fetchWithAuth('/api/universes')
      const data = await response.json()
      universes.value = data.universes
      if (universes.value.length > 0 && !universes.value.find(u => u.id === currentUniverse.value)) {
        currentUniverse.value = universes.value[0].id
      }
    } catch (e) {
      console.error('Failed to load universes:', e)
    }
  }

  async function loadFixtures() {
    try {
      const response = await fetchWithAuth('/api/fixtures')
      const data = await response.json()
      fixtures.value = data.fixtures
    } catch (e) {
      console.error('Failed to load fixtures:', e)
    }
  }

  async function loadPatches() {
    try {
      const response = await fetchWithAuth('/api/patch')
      const data = await response.json()
      patches.value = data.patches
    } catch (e) {
      console.error('Failed to load patches:', e)
    }
  }

  async function loadScenes() {
    try {
      const response = await fetchWithAuth('/api/scenes')
      const data = await response.json()
      scenes.value = data.scenes
    } catch (e) {
      console.error('Failed to load scenes:', e)
    }
  }

  async function loadChannelLabels(universeId) {
    try {
      const response = await fetchWithAuth(`/api/patch/labels/${universeId}`)
      const data = await response.json()
      channelLabels[universeId] = data.labels
    } catch (e) {
      console.error('Failed to load channel labels:', e)
    }
  }

  async function reloadAllChannelLabels() {
    for (const uid of Object.keys(channelLabels)) {
      await loadChannelLabels(parseInt(uid))
    }
  }

  async function createScene(name, transitionType = 'instant', duration = 0, universeIds = null) {
    try {
      const response = await fetchWithAuth('/api/scenes/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          transition_type: transitionType,
          duration,
          universe_ids: universeIds  // null = all universes
        })
      })
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to create scene')
      }
      const scene = await response.json()
      scenes.value.push(scene)
      return scene
    } catch (e) {
      console.error('Failed to create scene:', e)
      throw e
    }
  }

  async function recallScene(sceneId, options = {}) {
    try {
      const response = await fetchWithAuth(`/api/scenes/recall/${sceneId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(options)
      })
      return await response.json()
    } catch (e) {
      console.error('Failed to recall scene:', e)
      throw e
    }
  }

  async function updateScene(sceneId, universeIds = null, mergeMode = 'replace_all') {
    try {
      const response = await fetchWithAuth(`/api/scenes/update-current/${sceneId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          universe_ids: universeIds,
          merge_mode: mergeMode
        })
      })
      const scene = await response.json()
      const index = scenes.value.findIndex(s => s.id === sceneId)
      if (index !== -1) {
        scenes.value[index] = scene
      }
      return scene
    } catch (e) {
      console.error('Failed to update scene:', e)
      throw e
    }
  }

  async function deleteScene(sceneId) {
    try {
      await fetchWithAuth(`/api/scenes/${sceneId}`, { method: 'DELETE' })
      scenes.value = scenes.value.filter(s => s.id !== sceneId)
    } catch (e) {
      console.error('Failed to delete scene:', e)
      throw e
    }
  }

  async function toggleBlackout() {
    try {
      const response = await fetchWithAuth('/api/blackout', { method: 'POST' })
      const data = await response.json()
      blackoutActive.value = data.blackout
      return data.blackout
    } catch (e) {
      console.error('Failed to toggle blackout:', e)
      throw e
    }
  }

  async function checkBlackoutStatus() {
    try {
      const response = await fetchWithAuth('/api/blackout/status')
      const data = await response.json()
      blackoutActive.value = data.blackout
    } catch (e) {
      console.error('Failed to check blackout status:', e)
    }
  }

  function setChannel(channel, value) {
    wsManager.setChannel(currentUniverse.value, channel, value)
  }

  function setChannels(values) {
    wsManager.setChannels(currentUniverse.value, values)
  }

  function getChannelValue(channel) {
    return wsManager.getChannelValue(currentUniverse.value, channel)
  }

  function getAllValues() {
    return wsManager.getUniverseValues(currentUniverse.value)
  }

  function getChannelLabel(universeId, channel) {
    const labels = channelLabels[universeId]
    if (labels && labels[channel]) {
      return labels[channel].custom_label || labels[channel].label
    }
    return `Ch ${channel}`
  }

  function getChannelColor(universeId, channel) {
    const labels = channelLabels[universeId]
    if (labels && labels[channel] && labels[channel].color) {
      return labels[channel].color
    }
    return null
  }

  function getChannelGroupColor(universeId, channel) {
    const labels = channelLabels[universeId]
    if (labels && labels[channel] && labels[channel].groupColor) {
      return labels[channel].groupColor
    }
    return null
  }

  function getChannelFaderName(universeId, channel) {
    const labels = channelLabels[universeId]
    if (labels && labels[channel] && labels[channel].faderName) {
      return labels[channel].faderName
    }
    return null
  }

  function setActiveScene(sceneId) {
    activeScene.value = sceneId
  }

  function clearActiveScene() {
    activeScene.value = null
  }

  function startSceneRecallGracePeriod(durationMs = 0) {
    sceneRecallInProgress.value = true
    if (sceneRecallTimeout) clearTimeout(sceneRecallTimeout)
    // Grace period = scene duration + 1 second buffer for network latency
    const gracePeriod = durationMs + 1000
    sceneRecallTimeout = setTimeout(() => {
      sceneRecallInProgress.value = false
    }, gracePeriod)
  }

  // Input display and source tracking methods
  function setInputDisplayValues(universeId, values) {
    inputDisplayValues[universeId] = values
  }

  function setInputDisplayMode(universeId, enabled) {
    inputDisplayMode[universeId] = enabled
  }

  function setChannelSource(universeId, channel, source) {
    if (!channelSources[universeId]) {
      channelSources[universeId] = {}
    }
    channelSources[universeId][channel] = source
  }

  function getChannelSource(universeId, channel) {
    return channelSources[universeId]?.[channel] || 'unknown'
  }

  function isRemoteSource(universeId, channel) {
    const source = getChannelSource(universeId, channel)
    return source === 'input' || (source.startsWith('user_') && source !== `user_${myClientId.value}`)
  }

  function isLocalSource(universeId, channel) {
    const source = getChannelSource(universeId, channel)
    return source === `user_${myClientId.value}`
  }

  function setMyClientId(clientId) {
    myClientId.value = clientId
  }

  return {
    universes,
    fixtures,
    patches,
    scenes,
    currentUniverse,
    blackoutActive,
    channelLabels,
    loadUniverses,
    loadFixtures,
    loadPatches,
    loadScenes,
    loadChannelLabels,
    reloadAllChannelLabels,
    createScene,
    recallScene,
    updateScene,
    deleteScene,
    toggleBlackout,
    checkBlackoutStatus,
    setChannel,
    setChannels,
    getChannelValue,
    getAllValues,
    getChannelLabel,
    getChannelColor,
    getChannelGroupColor,
    getChannelFaderName,
    activeScene,
    setActiveScene,
    clearActiveScene,
    sceneRecallInProgress,
    startSceneRecallGracePeriod,
    // Input display and source tracking
    inputDisplayValues,
    inputDisplayMode,
    channelSources,
    myClientId,
    setInputDisplayValues,
    setInputDisplayMode,
    setChannelSource,
    getChannelSource,
    isRemoteSource,
    isLocalSource,
    setMyClientId
  }
})

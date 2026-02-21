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
  const inputBypassActive = ref(false)
  const globalGrandmaster = ref(255)
  const universeGrandmasters = reactive({})  // { universeId: 0-255 }
  const channelLabels = reactive({})
  const activeScene = ref(null)

  // Master fader colors
  const globalMasterFaderColor = ref('#f59e0b')  // Gold default
  const universeMasterFaderColors = reactive({})  // { universeId: color }

  // Park channels - locked to fixed values
  const parkedChannels = reactive({})  // { universeId: { channel: value } }

  // Highlight/Solo mode
  const highlightActive = ref(false)
  const highlightedChannels = reactive({})  // { universeId: [channels] }
  const highlightDimLevel = ref(0)

  // Scene recall grace period - prevents race conditions when recalling scenes
  const sceneRecallInProgress = ref(false)
  let sceneRecallTimeout = null

  // Input display and source tracking for fader status indicators
  const inputDisplayValues = reactive({})  // { universeId: [512 values] }
  const inputDisplayMode = reactive({})    // { universeId: boolean }
  const channelSources = reactive({})      // { universeId: { channel: "local"|"input"|"user_xxx" } }
  const myClientId = ref(null)             // This client's ID from WebSocket connection

  // Listen for bypass state changes from other clients
  wsManager.on('input_bypass_changed', (data) => {
    inputBypassActive.value = data.bypass
  })

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

  async function createScene(name, transitionType = 'instant', duration = 0, universeIds = null, groupIds = null, options = {}) {
    try {
      const response = await fetchWithAuth('/api/scenes/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name,
          transition_type: transitionType,
          duration,
          universe_ids: universeIds,  // null = all universes
          group_ids: groupIds,  // null = all enabled groups
          include_global_master: options.includeGlobalMaster || false,
          include_universe_masters: options.includeUniverseMasters || false
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

  async function updateScene(sceneId, universeIds = null, mergeMode = 'replace_all', groupIds = null, options = {}) {
    try {
      const response = await fetchWithAuth(`/api/scenes/update-current/${sceneId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          universe_ids: universeIds,
          merge_mode: mergeMode,
          group_ids: groupIds,
          include_global_master: options.includeGlobalMaster || false,
          include_universe_masters: options.includeUniverseMasters || false
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

  async function toggleInputBypass() {
    try {
      const newState = !inputBypassActive.value
      const response = await fetchWithAuth('/api/io/bypass', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bypass: newState })
      })
      const data = await response.json()
      inputBypassActive.value = data.bypass
      return data.bypass
    } catch (e) {
      console.error('Failed to toggle input bypass:', e)
      throw e
    }
  }

  async function checkInputBypassStatus() {
    try {
      const response = await fetchWithAuth('/api/io/bypass')
      const data = await response.json()
      inputBypassActive.value = data.bypass
    } catch (e) {
      console.error('Failed to check input bypass status:', e)
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

  // ============= Grand Master Control =============

  async function loadGrandmasters() {
    try {
      const response = await fetchWithAuth('/api/universes/grandmaster')
      const data = await response.json()
      globalGrandmaster.value = data.global ?? 255
      Object.assign(universeGrandmasters, data.universes || {})
    } catch (e) {
      console.error('Failed to load grandmasters:', e)
    }
  }

  function setGlobalGrandmaster(value) {
    globalGrandmaster.value = Math.max(0, Math.min(255, value))
    wsManager.send({
      type: 'set_global_grandmaster',
      value: globalGrandmaster.value
    })
  }

  function setUniverseGrandmaster(universeId, value) {
    const clampedValue = Math.max(0, Math.min(255, value))
    universeGrandmasters[universeId] = clampedValue
    wsManager.send({
      type: 'set_universe_grandmaster',
      universe_id: universeId,
      value: clampedValue
    })
  }

  function getUniverseGrandmaster(universeId) {
    return universeGrandmasters[universeId] ?? 255
  }

  // Listen for grandmaster changes from server
  wsManager.on('grandmaster_changed', (data) => {
    if (data.type === 'global') {
      globalGrandmaster.value = data.value
    } else if (data.type === 'universe' && data.universe_id !== undefined) {
      universeGrandmasters[data.universe_id] = data.value
    }
  })

  // Listen for park updates from server
  wsManager.on('park_update', (data) => {
    const { universe_id, channel, value, parked } = data
    if (!parkedChannels[universe_id]) {
      parkedChannels[universe_id] = {}
    }
    if (parked) {
      parkedChannels[universe_id][channel] = value
    } else {
      delete parkedChannels[universe_id][channel]
    }
  })

  // Listen for highlight updates from server
  wsManager.on('highlight_update', (data) => {
    highlightActive.value = data.active
    highlightDimLevel.value = data.dim_level || 0
    // Update highlighted channels
    Object.keys(highlightedChannels).forEach(k => delete highlightedChannels[k])
    if (data.channels) {
      Object.assign(highlightedChannels, data.channels)
    }
  })

  // ============= Master Fader Colors =============

  async function loadMasterFaderColors() {
    try {
      // Load global master fader color from settings
      const settingsResponse = await fetchWithAuth('/api/settings/global_master_fader_color')
      const settingsData = await settingsResponse.json()
      if (settingsData.value) {
        globalMasterFaderColor.value = settingsData.value
      }

      // Load universe master fader colors from I/O config
      const ioResponse = await fetchWithAuth('/api/io')
      const ioData = await ioResponse.json()
      for (const universe of ioData.universes || []) {
        if (universe.master_fader_color) {
          universeMasterFaderColors[universe.id] = universe.master_fader_color
        }
      }
    } catch (e) {
      console.error('Failed to load master fader colors:', e)
    }
  }

  async function setGlobalMasterFaderColor(color) {
    try {
      await fetchWithAuth('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'global_master_fader_color', value: color })
      })
      globalMasterFaderColor.value = color
    } catch (e) {
      console.error('Failed to save global master fader color:', e)
    }
  }

  async function setUniverseMasterFaderColor(universeId, color) {
    try {
      await fetchWithAuth(`/api/universes/${universeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ master_fader_color: color })
      })
      universeMasterFaderColors[universeId] = color
    } catch (e) {
      console.error('Failed to save universe master fader color:', e)
    }
  }

  function getUniverseMasterFaderColor(universeId) {
    return universeMasterFaderColors[universeId] || '#00bcd4'
  }

  // ============= Park Channels =============

  async function loadParkedChannels(universeId) {
    try {
      const response = await fetchWithAuth(`/api/dmx/parked/${universeId}`)
      const data = await response.json()
      parkedChannels[universeId] = data.parked || {}
    } catch (e) {
      console.error('Failed to load parked channels:', e)
    }
  }

  async function loadAllParkedChannels() {
    try {
      const response = await fetchWithAuth('/api/dmx/parked')
      const data = await response.json()
      Object.keys(parkedChannels).forEach(k => delete parkedChannels[k])
      Object.assign(parkedChannels, data.parked || {})
    } catch (e) {
      console.error('Failed to load parked channels:', e)
    }
  }

  async function parkChannel(universeId, channel, value) {
    try {
      const response = await fetchWithAuth('/api/dmx/park', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ universe_id: universeId, channel, value })
      })
      if (!response.ok) throw new Error('Failed to park channel')
      if (!parkedChannels[universeId]) {
        parkedChannels[universeId] = {}
      }
      parkedChannels[universeId][channel] = value
    } catch (e) {
      console.error('Failed to park channel:', e)
      throw e
    }
  }

  async function unparkChannel(universeId, channel) {
    try {
      const response = await fetchWithAuth('/api/dmx/unpark', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ universe_id: universeId, channel })
      })
      if (!response.ok) throw new Error('Failed to unpark channel')
      if (parkedChannels[universeId]) {
        delete parkedChannels[universeId][channel]
      }
    } catch (e) {
      console.error('Failed to unpark channel:', e)
      throw e
    }
  }

  function isChannelParked(universeId, channel) {
    return parkedChannels[universeId]?.[channel] !== undefined
  }

  function getParkedValue(universeId, channel) {
    return parkedChannels[universeId]?.[channel]
  }

  // ============= Highlight/Solo =============

  async function loadHighlightState() {
    try {
      const response = await fetchWithAuth('/api/dmx/highlight')
      const data = await response.json()
      highlightActive.value = data.active
      highlightDimLevel.value = data.dim_level || 0
      Object.keys(highlightedChannels).forEach(k => delete highlightedChannels[k])
      if (data.channels) {
        Object.assign(highlightedChannels, data.channels)
      }
    } catch (e) {
      console.error('Failed to load highlight state:', e)
    }
  }

  async function startHighlight(universeId, channels, dimLevel = 0) {
    try {
      const response = await fetchWithAuth('/api/dmx/highlight', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ universe_id: universeId, channels, dim_level: dimLevel })
      })
      if (!response.ok) throw new Error('Failed to start highlight')
      highlightActive.value = true
      highlightDimLevel.value = dimLevel
      if (!highlightedChannels[universeId]) {
        highlightedChannels[universeId] = []
      }
      highlightedChannels[universeId] = [...new Set([...highlightedChannels[universeId], ...channels])]
    } catch (e) {
      console.error('Failed to start highlight:', e)
      throw e
    }
  }

  async function addToHighlight(universeId, channel) {
    try {
      const response = await fetchWithAuth('/api/dmx/highlight/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ universe_id: universeId, channel })
      })
      if (!response.ok) throw new Error('Failed to add to highlight')
      highlightActive.value = true
      if (!highlightedChannels[universeId]) {
        highlightedChannels[universeId] = []
      }
      if (!highlightedChannels[universeId].includes(channel)) {
        highlightedChannels[universeId].push(channel)
      }
    } catch (e) {
      console.error('Failed to add to highlight:', e)
      throw e
    }
  }

  async function removeFromHighlight(universeId, channel) {
    try {
      const response = await fetchWithAuth('/api/dmx/highlight/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ universe_id: universeId, channel })
      })
      if (!response.ok) throw new Error('Failed to remove from highlight')
      if (highlightedChannels[universeId]) {
        highlightedChannels[universeId] = highlightedChannels[universeId].filter(c => c !== channel)
      }
      // Check if any channels still highlighted
      const anyHighlighted = Object.values(highlightedChannels).some(arr => arr && arr.length > 0)
      if (!anyHighlighted) {
        highlightActive.value = false
      }
    } catch (e) {
      console.error('Failed to remove from highlight:', e)
      throw e
    }
  }

  async function stopHighlight() {
    try {
      const response = await fetchWithAuth('/api/dmx/highlight/stop', {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to stop highlight')
      highlightActive.value = false
      Object.keys(highlightedChannels).forEach(k => delete highlightedChannels[k])
    } catch (e) {
      console.error('Failed to stop highlight:', e)
      throw e
    }
  }

  // Group park/highlight methods
  async function highlightGroup(groupId) {
    try {
      const response = await fetchWithAuth(`/api/groups/${groupId}/highlight`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to highlight group')
      // State will be updated via WebSocket broadcast
    } catch (e) {
      console.error('Failed to highlight group:', e)
      throw e
    }
  }

  async function stopHighlightGroup(groupId) {
    try {
      const response = await fetchWithAuth(`/api/groups/${groupId}/highlight/stop`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to stop group highlight')
      // State will be updated via WebSocket broadcast
    } catch (e) {
      console.error('Failed to stop group highlight:', e)
      throw e
    }
  }

  async function parkGroup(groupId) {
    try {
      const response = await fetchWithAuth(`/api/groups/${groupId}/park`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to park group')
      // State will be updated via WebSocket broadcast
    } catch (e) {
      console.error('Failed to park group:', e)
      throw e
    }
  }

  async function unparkGroup(groupId) {
    try {
      const response = await fetchWithAuth(`/api/groups/${groupId}/unpark`, {
        method: 'POST'
      })
      if (!response.ok) throw new Error('Failed to unpark group')
      // State will be updated via WebSocket broadcast
    } catch (e) {
      console.error('Failed to unpark group:', e)
      throw e
    }
  }

  function isChannelHighlighted(universeId, channel) {
    return highlightedChannels[universeId]?.includes(channel) || false
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
    inputBypassActive,
    toggleInputBypass,
    checkInputBypassStatus,
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
    setMyClientId,
    // Grand Master control
    globalGrandmaster,
    universeGrandmasters,
    loadGrandmasters,
    setGlobalGrandmaster,
    setUniverseGrandmaster,
    getUniverseGrandmaster,
    // Master Fader Colors
    globalMasterFaderColor,
    universeMasterFaderColors,
    loadMasterFaderColors,
    setGlobalMasterFaderColor,
    setUniverseMasterFaderColor,
    getUniverseMasterFaderColor,
    // Park Channels
    parkedChannels,
    loadParkedChannels,
    loadAllParkedChannels,
    parkChannel,
    unparkChannel,
    isChannelParked,
    getParkedValue,
    // Highlight/Solo
    highlightActive,
    highlightedChannels,
    highlightDimLevel,
    loadHighlightState,
    startHighlight,
    addToHighlight,
    removeFromHighlight,
    stopHighlight,
    isChannelHighlighted,
    // Group Park/Highlight
    highlightGroup,
    stopHighlightGroup,
    parkGroup,
    unparkGroup
  }
})

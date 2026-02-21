<template>
  <div>
    <div class="fader-header">
      <div class="header-top">
        <h2 class="card-title">Fader Control</h2>
        <div class="header-right">
          <button
            v-if="hasParkedChannels"
            class="btn btn-small btn-park-active"
            title="Channels are parked"
          >
            PARKED
          </button>
          <button
            v-if="dmxStore.highlightActive"
            class="btn btn-small btn-highlight-active"
            :class="{ 'btn-no-click': !authStore.canHighlight }"
            @click="authStore.canHighlight && dmxStore.stopHighlight()"
            :title="authStore.canHighlight ? 'Click to exit highlight/solo mode' : 'Highlight mode active (no permission to change)'"
          >
            HIGHLIGHT
          </button>
          <button
            v-if="authStore.canBypass"
            class="btn btn-small"
            :class="dmxStore.inputBypassActive ? 'btn-bypass-active' : 'btn-secondary'"
            @click="toggleBypass"
            title="Temporarily stop external DMX input from affecting output"
          >
            {{ dmxStore.inputBypassActive ? 'BYPASS ON' : 'Bypass Inputs' }}
          </button>
          <button
            v-else-if="dmxStore.inputBypassActive"
            class="btn btn-small btn-bypass-active btn-no-click"
            title="Bypass mode active (no permission to change)"
          >
            BYPASS ON
          </button>
          <button class="btn btn-small btn-secondary" @click="showUniverseJump = true">Jump</button>
          <div class="per-page-control">
            <input
              type="number"
              class="form-input"
              v-model.number="channelsPerPage"
              min="1"
              max="512"
              style="width: 60px;"
            >
            <span style="font-size: 12px; color: var(--text-secondary);">per page</span>
          </div>
        </div>
      </div>
      <div class="universe-tabs">
        <button
          v-for="universe in dmxStore.universes"
          :key="universe.id"
          class="universe-tab"
          :class="{ active: dmxStore.currentUniverse === universe.id }"
          @click="selectUniverse(universe.id)"
        >
          {{ universe.label }}
        </button>
      </div>
    </div>

    <!-- Universe Jump Popup -->
    <div v-if="showUniverseJump" class="modal-overlay" @click.self="showUniverseJump = false">
      <div class="jump-popup">
        <div class="jump-popup-header">
          <h4>Select Universe</h4>
          <button class="modal-close" @click="showUniverseJump = false">&times;</button>
        </div>
        <div class="jump-popup-list">
          <button
            v-for="u in dmxStore.universes"
            :key="u.id"
            class="jump-popup-item"
            :class="{ selected: dmxStore.currentUniverse === u.id }"
            @click="jumpToUniverse(u.id)"
          >
            {{ u.label }}
          </button>
        </div>
      </div>
    </div>

    <!-- Channel range selector -->
    <div class="card" style="margin-bottom: 16px; padding: 12px;">
      <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
        <span style="color: var(--text-secondary);">Channels:</span>
        <button
          v-for="range in channelRanges"
          :key="range.start"
          class="btn btn-small"
          :class="currentRange.start === range.start ? 'btn-primary' : 'btn-secondary'"
          @click="currentRange = range"
        >
          {{ range.start }}-{{ range.end }}
        </button>
      </div>
    </div>

    <!-- Faders -->
    <div class="card" style="overflow-x: auto;">
      <div class="fader-grid">
        <div
          v-for="channel in visibleChannels"
          :key="channel"
          class="fader-container"
        >
          <!-- Status indicator lights -->
          <div class="fader-indicators">
            <span
              class="indicator indicator-remote"
              :class="{ active: isRemoteActive(channel) }"
              title="External DMX input"
            ></span>
            <span
              class="indicator indicator-local"
              :class="{ active: isLocalActive(channel) }"
              title="DMXX control"
            ></span>
            <span
              class="indicator indicator-group"
              :class="{ active: isGroupActive(channel) }"
              title="Group/Master control"
            ></span>
          </div>
          <span class="fader-label" :title="getLabel(channel)">{{ channel }}</span>
          <span class="fader-name" :class="{ 'fader-name-placeholder': !getFaderName(channel) }" :title="getLabel(channel)">{{ getFaderName(channel) || '—' }}</span>
          <button class="fader-btn" @click="increment(channel)">+</button>
          <div
            class="fader-track"
            :style="getTrackStyle(channel)"
            @mousedown="startDrag($event, channel)"
            @touchstart="startDrag($event, channel)"
          >
            <div
              class="fader-fill"
              :style="{ height: (displayValues[channel - 1] / 255 * 100) + '%', background: getChannelColor(channel) }"
            ></div>
          </div>
          <button class="fader-btn" @click="decrement(channel)">-</button>
          <div class="fader-footer">
            <button
              v-if="authStore.canPark"
              class="park-btn"
              :class="{ active: dmxStore.isChannelParked(dmxStore.currentUniverse, channel) }"
              @mousedown="startParkPress(channel)"
              @mouseup="endParkPress(channel)"
              @mouseleave="cancelParkPress(channel)"
              @touchstart.prevent="startParkPress(channel)"
              @touchend.prevent="endParkPress(channel)"
              @touchcancel="cancelParkPress(channel)"
              title="Long-press to park channel at current value"
            >P</button>
            <span class="fader-value">
              <span class="fader-percent">{{ Math.round(displayValues[channel - 1] / 255 * 100) }}%</span>
              <span class="fader-raw">{{ displayValues[channel - 1] }}</span>
            </span>
            <button
              v-if="authStore.canHighlight"
              class="highlight-btn"
              :class="{ active: dmxStore.isChannelHighlighted(dmxStore.currentUniverse, channel) }"
              @mousedown="startHighlightPress(channel)"
              @mouseup="endHighlightPress(channel)"
              @mouseleave="cancelHighlightPress(channel)"
              @touchstart.prevent="startHighlightPress(channel)"
              @touchend.prevent="endHighlightPress(channel)"
              @touchcancel="cancelHighlightPress(channel)"
              title="Long-press to highlight/solo this channel"
            >H</button>
          </div>
          <div
            v-if="getChannelGroupColor(channel)"
            class="fader-group-stripe"
            :class="{
              'connects-left': hasSameGroupColorLeft(channel),
              'connects-right': hasSameGroupColorRight(channel)
            }"
            :style="{ backgroundColor: getChannelGroupColor(channel) }"
          ></div>
        </div>

        <!-- Universe Master Fader -->
        <div
          class="fader-container master-fader universe-master"
          :style="{ borderColor: dmxStore.getUniverseMasterFaderColor(dmxStore.currentUniverse) }"
        >
          <span class="fader-label master-label" :style="{ color: dmxStore.getUniverseMasterFaderColor(dmxStore.currentUniverse) }">U</span>
          <span class="fader-name">Universe</span>
          <button class="fader-btn" @click="incrementUniverseMaster">+</button>
          <div
            class="fader-track master-track"
            @mousedown="startMasterDrag($event, 'universe')"
            @touchstart="startMasterDrag($event, 'universe')"
          >
            <div
              class="fader-fill"
              :style="{ height: (dmxStore.getUniverseGrandmaster(dmxStore.currentUniverse) / 255 * 100) + '%', background: dmxStore.getUniverseMasterFaderColor(dmxStore.currentUniverse) }"
            ></div>
          </div>
          <button class="fader-btn" @click="decrementUniverseMaster">-</button>
          <span class="fader-value">
            <span class="fader-percent">{{ Math.round(dmxStore.getUniverseGrandmaster(dmxStore.currentUniverse) / 255 * 100) }}%</span>
            <span class="fader-raw">{{ dmxStore.getUniverseGrandmaster(dmxStore.currentUniverse) }}</span>
          </span>
        </div>

        <!-- Global Master Fader -->
        <div
          class="fader-container master-fader global-master"
          :style="{ borderColor: dmxStore.globalMasterFaderColor }"
        >
          <span class="fader-label master-label" :style="{ color: dmxStore.globalMasterFaderColor }">G</span>
          <span class="fader-name">Global</span>
          <button class="fader-btn" @click="incrementGlobalMaster">+</button>
          <div
            class="fader-track master-track"
            @mousedown="startMasterDrag($event, 'global')"
            @touchstart="startMasterDrag($event, 'global')"
          >
            <div
              class="fader-fill"
              :style="{ height: (dmxStore.globalGrandmaster / 255 * 100) + '%', background: dmxStore.globalMasterFaderColor }"
            ></div>
          </div>
          <button class="fader-btn" @click="decrementGlobalMaster">-</button>
          <span class="fader-value">
            <span class="fader-percent">{{ Math.round(dmxStore.globalGrandmaster / 255 * 100) }}%</span>
            <span class="fader-raw">{{ dmxStore.globalGrandmaster }}</span>
          </span>
        </div>
      </div>
    </div>

    <!-- Quick actions -->
    <div class="card" style="margin-top: 16px; padding: 12px;">
      <div style="display: flex; gap: 12px; flex-wrap: wrap;">
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: nowrap;">
          <span style="font-size: 12px; color: var(--text-secondary);">Page:</span>
          <button class="btn btn-secondary btn-small" @click="setAllVisible(0)">Zero</button>
          <button class="btn btn-secondary btn-small" @click="setAllVisible(64)">25%</button>
          <button class="btn btn-secondary btn-small" @click="setAllVisible(128)">50%</button>
          <button class="btn btn-secondary btn-small" @click="setAllVisible(191)">75%</button>
          <button class="btn btn-secondary btn-small" @click="setAllVisible(255)">Full</button>
        </div>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: nowrap;">
          <span style="font-size: 12px; color: var(--text-secondary);">Universe:</span>
          <button class="btn btn-secondary btn-small" @click="setAllUniverse(0)">Zero</button>
          <button class="btn btn-secondary btn-small" @click="setAllUniverse(64)">25%</button>
          <button class="btn btn-secondary btn-small" @click="setAllUniverse(128)">50%</button>
          <button class="btn btn-secondary btn-small" @click="setAllUniverse(191)">75%</button>
          <button class="btn btn-secondary btn-small" @click="setAllUniverse(255)">Full</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useDmxStore } from '../stores/dmx.js'
import { useAuthStore } from '../stores/auth.js'
import { wsManager } from '../websocket.js'

const dmxStore = useDmxStore()
const authStore = useAuthStore()

// Cookie helpers for per-page persistence
function setCookie(name, value, days = 365) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`
}

function getCookie(name) {
  const match = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
  return match ? decodeURIComponent(match[2]) : null
}

const values = ref(new Array(512).fill(0))
const inputValues = ref(new Array(512).fill(0))
const dragging = ref(null)
const masterDragging = ref(null)  // For master fader dragging
const channelsPerPage = ref(parseInt(getCookie('dmxx_channelsPerPage')) || 64)
const currentRange = ref({ start: 1, end: Math.min(channelsPerPage.value - 2, 512) })
const remoteActiveChannels = ref({})  // { channel: true } for blue light indicator
const localActiveChannels = ref({})   // { channel: timeoutId } for yellow light fade
const groupActiveChannels = ref({})   // { channel: timeoutId } for green light fade (group control)
let pendingRemoteIndicatorClear = null  // Single timeout for clearing remote indicators
let lastRemoteChangedChannels = []  // Channels from last input update
let activeSceneClearTimeout = null  // Debounce active scene clear to avoid flooding WebSocket
const showUniverseJump = ref(false)
const pendingChannelUpdates = ref({})  // Debounce buffer for channel updates
let channelUpdateTimeout = null

const channelRanges = computed(() => {
  const ranges = []
  const channelCount = Math.max(1, channelsPerPage.value - 2)  // Reserve 2 slots for masters
  for (let start = 1; start <= 512; start += channelCount) {
    const end = Math.min(start + channelCount - 1, 512)
    ranges.push({ start, end })
  }
  return ranges
})

watch(channelsPerPage, (newVal) => {
  if (newVal < 3) channelsPerPage.value = 3  // Minimum: 1 channel + 2 masters
  else if (newVal > 514) channelsPerPage.value = 514  // Max: 512 channels + 2 masters
  setCookie('dmxx_channelsPerPage', channelsPerPage.value.toString())
  currentRange.value = channelRanges.value[0]
})

const visibleChannels = computed(() => {
  const channels = []
  for (let i = currentRange.value.start; i <= currentRange.value.end; i++) {
    channels.push(i)
  }
  return channels
})

const displayValues = computed(() => {
  if (wsManager.blackoutActive.value) {
    return new Array(512).fill(0)
  }

  const universeId = dmxStore.currentUniverse

  // When highlight is active, show highlight-adjusted values (but respect park)
  if (dmxStore.highlightActive) {
    return values.value.map((val, i) => {
      const channel = i + 1
      // Park takes priority over highlight
      if (dmxStore.isChannelParked(universeId, channel)) {
        return dmxStore.getParkedValue(universeId, channel)
      }
      if (dmxStore.isChannelHighlighted(universeId, channel)) {
        return 255  // Highlighted channels go to full
      }
      return dmxStore.highlightDimLevel  // Others go to dim level (0)
    })
  }

  // Show raw local values - backend handles HTP/LTP merging for output
  return values.value
})

const hasParkedChannels = computed(() => {
  return Object.keys(dmxStore.parkedChannels).some(uid =>
    Object.keys(dmxStore.parkedChannels[uid] || {}).length > 0
  )
})

onMounted(async () => {
  await dmxStore.loadChannelLabels(dmxStore.currentUniverse)
  dmxStore.checkInputBypassStatus()
  dmxStore.loadGrandmasters()
  dmxStore.loadMasterFaderColors()
  dmxStore.loadAllParkedChannels()
  dmxStore.loadHighlightState()
  wsManager.on('channel_change', handleChannelChange)
  wsManager.on('values', handleValues)
  wsManager.on('all_values', handleAllValues)
  wsManager.on('input_to_ui', handleInputToUI)
  wsManager.on('blackout', handleBlackout)

  // Load values - they may already be available
  loadValues()
  // Also request fresh values in case WebSocket just connected
  wsManager.requestValues(dmxStore.currentUniverse)

  document.addEventListener('mousemove', handleDrag)
  document.addEventListener('mouseup', stopDrag)
  document.addEventListener('touchmove', handleDrag)
  document.addEventListener('touchend', stopDrag)
})

onUnmounted(() => {
  wsManager.off('channel_change', handleChannelChange)
  wsManager.off('values', handleValues)
  wsManager.off('all_values', handleAllValues)
  wsManager.off('input_to_ui', handleInputToUI)
  wsManager.off('blackout', handleBlackout)

  document.removeEventListener('mousemove', handleDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', handleDrag)
  document.removeEventListener('touchend', stopDrag)
})

function loadValues() {
  values.value = wsManager.getUniverseValues(dmxStore.currentUniverse)
}

async function selectUniverse(id) {
  dmxStore.currentUniverse = id
  wsManager.requestValues(id)
  loadValues()
  inputValues.value = new Array(512).fill(0)
  await dmxStore.loadChannelLabels(id)
}

function jumpToUniverse(id) {
  selectUniverse(id)
  showUniverseJump.value = false
}

async function toggleBypass() {
  try {
    await dmxStore.toggleInputBypass()
  } catch (e) {
    console.error('Failed to toggle bypass:', e)
  }
}

function handleChannelChange(data) {
  if (data.universe_id === dmxStore.currentUniverse) {
    values.value[data.channel - 1] = data.value
    const channel = data.channel

    // If we're dragging this channel and backend rejected it (input-controlled group),
    // stop the drag to prevent overwriting the snapped-back value.
    // Only cancel on "group_reject", not "group" (normal group updates should allow smooth dragging)
    if (data.source === 'group_reject' && dragging.value && dragging.value.channel === channel) {
      dragging.value = null
    }

    // Set timeout for appropriate indicator based on source
    if (data.source === 'group' || data.source === 'group_reject') {
      // Green indicator for group/master control
      if (groupActiveChannels.value[channel]) {
        clearTimeout(groupActiveChannels.value[channel])
      }
      groupActiveChannels.value[channel] = setTimeout(() => {
        delete groupActiveChannels.value[channel]
      }, 500)
    } else if (data.source && (data.source.startsWith('user_') || data.source === 'local')) {
      // Yellow indicator for DMXX sources (user_* or local/scene recall)
      if (localActiveChannels.value[channel]) {
        clearTimeout(localActiveChannels.value[channel])
      }
      localActiveChannels.value[channel] = setTimeout(() => {
        delete localActiveChannels.value[channel]
      }, 500)
    }
  }
}

function handleValues(data) {
  if (data.universe_id === dmxStore.currentUniverse) {
    const oldValues = values.value
    values.value = [...data.values]
    // Flash green light for channels that changed (e.g., scene recall)
    for (let i = 0; i < data.values.length; i++) {
      if (data.values[i] !== oldValues[i]) {
        const channel = i + 1
        if (localActiveChannels.value[channel]) {
          clearTimeout(localActiveChannels.value[channel])
        }
        localActiveChannels.value[channel] = setTimeout(() => {
          delete localActiveChannels.value[channel]
        }, 500)
      }
    }
  }
}

function handleAllValues(data) {
  if (data[dmxStore.currentUniverse]) {
    values.value = [...data[dmxStore.currentUniverse]]
  }
}

function handleInputToUI(data) {
  if (data.universe_id === dmxStore.currentUniverse) {
    const newValues = data.values
    const changedChannels = []

    // Find changed channels by comparing against displayed values (not last input)
    // This ensures faders snap back to input even when input=0 and user moved fader
    // Skip channels with -1 value (outside input range)
    for (let i = 0; i < newValues.length; i++) {
      // -1 means "don't update this channel" (outside input range)
      if (newValues[i] === -1) continue
      if (newValues[i] !== values.value[i]) {
        changedChannels.push(i + 1)
        // Update individual value - avoids triggering re-render of ALL faders
        values.value[i] = newValues[i]
      }
    }

    if (changedChannels.length > 0) {
      // Clear active scene since DMX input changed values (debounced to avoid flooding)
      if (!activeSceneClearTimeout) {
        wsManager.setActiveScene(null)
        activeSceneClearTimeout = setTimeout(() => {
          activeSceneClearTimeout = null
        }, 100)  // Only send once per 100ms
      }

      // Clear previous indicator timeout
      if (pendingRemoteIndicatorClear) {
        clearTimeout(pendingRemoteIndicatorClear)
        for (const ch of lastRemoteChangedChannels) {
          delete remoteActiveChannels.value[ch]
        }
      }

      // Mark changed channels as remote active
      for (const ch of changedChannels) {
        remoteActiveChannels.value[ch] = true
      }
      lastRemoteChangedChannels = changedChannels

      // Single timeout to clear all indicators after 500ms
      pendingRemoteIndicatorClear = setTimeout(() => {
        for (const ch of lastRemoteChangedChannels) {
          delete remoteActiveChannels.value[ch]
        }
        pendingRemoteIndicatorClear = null
        lastRemoteChangedChannels = []
      }, 500)
    }

    inputValues.value = [...newValues]
  }
}

function isRemoteActive(channel) {
  return !!remoteActiveChannels.value[channel]
}

function isLocalActive(channel) {
  return !!localActiveChannels.value[channel]
}

function isGroupActive(channel) {
  return !!groupActiveChannels.value[channel]
}

function handleBlackout(data) {
  // Flash green lights on all visible channels when blackout is toggled
  for (const channel of visibleChannels.value) {
    if (localActiveChannels.value[channel]) {
      clearTimeout(localActiveChannels.value[channel])
    }
    localActiveChannels.value[channel] = setTimeout(() => {
      delete localActiveChannels.value[channel]
    }, 500)
  }
}

function setChannel(channel, value) {
  value = Math.max(0, Math.min(255, value))
  const oldValue = values.value[channel - 1]
  if (value !== oldValue) {
    // Immediate local update for responsive UI
    values.value[channel - 1] = value

    // Queue the channel update for debounced send
    pendingChannelUpdates.value[channel] = value

    // Debounce the actual WebSocket send
    if (channelUpdateTimeout) clearTimeout(channelUpdateTimeout)
    channelUpdateTimeout = setTimeout(() => {
      const updates = { ...pendingChannelUpdates.value }
      pendingChannelUpdates.value = {}
      if (Object.keys(updates).length > 0) {
        dmxStore.setChannels(updates)  // Send all pending as batch
      }
    }, 30)  // 30ms debounce like Groups

    // Only clear active scene if we're not in a scene recall grace period
    if (!dmxStore.sceneRecallInProgress) {
      wsManager.setActiveScene(null)
    }
  }
}

function increment(channel) {
  const current = values.value[channel - 1]
  setChannel(channel, Math.min(255, current + 5))
}

function decrement(channel) {
  const current = values.value[channel - 1]
  setChannel(channel, Math.max(0, current - 5))
}

function setAllVisible(value) {
  const channelValues = {}
  let anyChanged = false
  for (const channel of visibleChannels.value) {
    if (values.value[channel - 1] !== value) {
      anyChanged = true
    }
    channelValues[channel] = value
    values.value[channel - 1] = value
  }
  if (anyChanged) {
    dmxStore.setChannels(channelValues)
    // Only clear active scene if we're not in a scene recall grace period
    if (!dmxStore.sceneRecallInProgress) {
      wsManager.setActiveScene(null)
    }
  }
}

function setAllUniverse(value) {
  const channelValues = {}
  let anyChanged = false
  for (let channel = 1; channel <= 512; channel++) {
    if (values.value[channel - 1] !== value) {
      anyChanged = true
    }
    channelValues[channel] = value
    values.value[channel - 1] = value
  }
  if (anyChanged) {
    dmxStore.setChannels(channelValues)
    if (!dmxStore.sceneRecallInProgress) {
      wsManager.setActiveScene(null)
    }
  }
}

function startDrag(event, channel) {
  event.preventDefault()
  dragging.value = { channel, element: event.target.closest('.fader-track') }
  handleDrag(event)
}

function handleDrag(event) {
  // Handle channel fader dragging
  if (dragging.value) {
    event.preventDefault()
    const { channel, element } = dragging.value
    const rect = element.getBoundingClientRect()
    const clientY = event.touches ? event.touches[0].clientY : event.clientY
    const y = rect.bottom - clientY
    const height = rect.height
    const value = Math.round(Math.max(0, Math.min(255, (y / height) * 255)))
    setChannel(channel, value)
  }

  // Handle master fader dragging
  if (masterDragging.value) {
    event.preventDefault()
    const { type, element } = masterDragging.value
    const rect = element.getBoundingClientRect()
    const clientY = event.touches ? event.touches[0].clientY : event.clientY
    const y = rect.bottom - clientY
    const height = rect.height
    const value = Math.round(Math.max(0, Math.min(255, (y / height) * 255)))

    if (type === 'universe') {
      dmxStore.setUniverseGrandmaster(dmxStore.currentUniverse, value)
    } else if (type === 'global') {
      dmxStore.setGlobalGrandmaster(value)
    }
  }
}

function stopDrag() {
  dragging.value = null
  masterDragging.value = null
}

// Master fader functions
function startMasterDrag(event, type) {
  event.preventDefault()
  masterDragging.value = { type, element: event.target.closest('.fader-track') }
  handleDrag(event)
}

function incrementUniverseMaster() {
  const current = dmxStore.getUniverseGrandmaster(dmxStore.currentUniverse)
  dmxStore.setUniverseGrandmaster(dmxStore.currentUniverse, Math.min(255, current + 5))
}

function decrementUniverseMaster() {
  const current = dmxStore.getUniverseGrandmaster(dmxStore.currentUniverse)
  dmxStore.setUniverseGrandmaster(dmxStore.currentUniverse, Math.max(0, current - 5))
}

function incrementGlobalMaster() {
  const current = dmxStore.globalGrandmaster
  dmxStore.setGlobalGrandmaster(Math.min(255, current + 5))
}

function decrementGlobalMaster() {
  const current = dmxStore.globalGrandmaster
  dmxStore.setGlobalGrandmaster(Math.max(0, current - 5))
}

function getLabel(channel) {
  return dmxStore.getChannelLabel(dmxStore.currentUniverse, channel)
}

function getChannelColor(channel) {
  return dmxStore.getChannelColor(dmxStore.currentUniverse, channel) || 'var(--accent)'
}

function getChannelGroupColor(channel) {
  return dmxStore.getChannelGroupColor(dmxStore.currentUniverse, channel)
}

function hasSameGroupColorLeft(channel) {
  const currentColor = dmxStore.getChannelGroupColor(dmxStore.currentUniverse, channel)
  const leftColor = dmxStore.getChannelGroupColor(dmxStore.currentUniverse, channel - 1)
  return currentColor && leftColor && currentColor === leftColor
}

function hasSameGroupColorRight(channel) {
  const currentColor = dmxStore.getChannelGroupColor(dmxStore.currentUniverse, channel)
  const rightColor = dmxStore.getChannelGroupColor(dmxStore.currentUniverse, channel + 1)
  return currentColor && rightColor && currentColor === rightColor
}

function getTrackStyle(channel) {
  const color = dmxStore.getChannelColor(dmxStore.currentUniverse, channel)
  if (color) {
    return { boxShadow: `inset 0 0 0 2px ${color}` }
  }
  return {}
}

function getFaderName(channel) {
  return dmxStore.getChannelFaderName(dmxStore.currentUniverse, channel) || ''
}

function isRemoteSource(channel) {
  return wsManager.isRemoteSource(dmxStore.currentUniverse, channel)
}

function isLocalSource(channel) {
  return wsManager.isLocalSource(dmxStore.currentUniverse, channel)
}

// ========== Park/Highlight Long-Press Handling ==========

const LONG_PRESS_DURATION = 500  // ms

// Park button state
const parkPressTimers = ref({})  // { channel: timeoutId }
const parkPressStarted = ref({})  // { channel: timestamp }

function startParkPress(channel) {
  parkPressStarted.value[channel] = Date.now()
  parkPressTimers.value[channel] = setTimeout(async () => {
    // Long press detected - toggle park
    if (dmxStore.isChannelParked(dmxStore.currentUniverse, channel)) {
      await dmxStore.unparkChannel(dmxStore.currentUniverse, channel)
    } else {
      const currentValue = values.value[channel - 1]
      await dmxStore.parkChannel(dmxStore.currentUniverse, channel, currentValue)
    }
    // Clear to prevent short-click action
    delete parkPressStarted.value[channel]
    delete parkPressTimers.value[channel]
  }, LONG_PRESS_DURATION)
}

function endParkPress(channel) {
  const timer = parkPressTimers.value[channel]
  if (timer) {
    clearTimeout(timer)
    delete parkPressTimers.value[channel]
  }

  // Check if it was a short click on an active parked channel
  const startTime = parkPressStarted.value[channel]
  if (startTime && Date.now() - startTime < LONG_PRESS_DURATION) {
    // Short click - if parked, unpark
    if (dmxStore.isChannelParked(dmxStore.currentUniverse, channel)) {
      dmxStore.unparkChannel(dmxStore.currentUniverse, channel)
    }
  }
  delete parkPressStarted.value[channel]
}

function cancelParkPress(channel) {
  const timer = parkPressTimers.value[channel]
  if (timer) {
    clearTimeout(timer)
    delete parkPressTimers.value[channel]
  }
  delete parkPressStarted.value[channel]
}

// Highlight button state
const highlightPressTimers = ref({})  // { channel: timeoutId }
const highlightPressStarted = ref({})  // { channel: timestamp }

function startHighlightPress(channel) {
  highlightPressStarted.value[channel] = Date.now()
  highlightPressTimers.value[channel] = setTimeout(async () => {
    // Long press detected - toggle highlight
    try {
      if (dmxStore.isChannelHighlighted(dmxStore.currentUniverse, channel)) {
        await dmxStore.removeFromHighlight(dmxStore.currentUniverse, channel)
      } else {
        await dmxStore.addToHighlight(dmxStore.currentUniverse, channel)
      }
    } catch (e) {
      console.error('Highlight error:', e)
    }
    // Clear to prevent short-click action
    delete highlightPressStarted.value[channel]
    delete highlightPressTimers.value[channel]
  }, LONG_PRESS_DURATION)
}

function endHighlightPress(channel) {
  const timer = highlightPressTimers.value[channel]
  if (timer) {
    clearTimeout(timer)
    delete highlightPressTimers.value[channel]
  }

  // Check if it was a short click on an active highlighted channel
  const startTime = highlightPressStarted.value[channel]
  if (startTime && Date.now() - startTime < LONG_PRESS_DURATION) {
    // Short click - if highlighted, remove from highlight
    if (dmxStore.isChannelHighlighted(dmxStore.currentUniverse, channel)) {
      dmxStore.removeFromHighlight(dmxStore.currentUniverse, channel)
    }
  }
  delete highlightPressStarted.value[channel]
}

function cancelHighlightPress(channel) {
  const timer = highlightPressTimers.value[channel]
  if (timer) {
    clearTimeout(timer)
    delete highlightPressTimers.value[channel]
  }
  delete highlightPressStarted.value[channel]
}
</script>

<style scoped>
input[type="range"] {
  -webkit-appearance: none;
  background: var(--fader-bg);
  height: 6px;
  border-radius: 3px;
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  background: var(--accent);
  border-radius: 50%;
  cursor: pointer;
}

.fader-name {
  font-size: 10px;
  color: var(--text-primary);
  margin-bottom: 2px;
  text-align: center;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-height: 12px;
  font-weight: bold;
}

.fader-name-placeholder {
  opacity: 0.3;
}

.fader-percent {
  display: block;
  font-size: 10px;
  font-weight: bold;
  color: var(--text-primary);
}

.fader-raw {
  display: block;
  font-size: 9px;
  font-weight: normal;
  color: var(--text-secondary);
}

/* Status indicator lights */
.fader-indicators {
  position: absolute;
  top: -2px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  gap: 4px;
  pointer-events: none;
  z-index: 1;
}

.indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  opacity: 0.2;
  transition: opacity 0.5s ease-out, box-shadow 0.5s ease-out;
}

.indicator-remote {
  background: var(--indicator-remote);
}

.indicator-local {
  background: var(--indicator-local);
}

.indicator-group {
  background: var(--indicator-group, #4ade80);  /* Green for group control */
}

.indicator.active {
  opacity: 1;
  box-shadow: 0 0 4px currentColor;
  transition: opacity 0.1s ease-in, box-shadow 0.1s ease-in;
}

.indicator-remote.active {
  box-shadow: 0 0 4px var(--indicator-remote);
}

.indicator-local.active {
  box-shadow: 0 0 4px var(--indicator-local);
}

.indicator-group.active {
  box-shadow: 0 0 4px var(--indicator-group, #4ade80);
}

.fader-group-stripe {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 4px;
  border-radius: 0 0 4px 4px;
}

.fader-group-stripe.connects-left {
  left: -4px;
  border-bottom-left-radius: 0;
}

.fader-group-stripe.connects-right {
  right: -4px;
  border-bottom-right-radius: 0;
}

.fader-header {
  margin-bottom: 16px;
}

.header-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
  margin-bottom: 12px;
}

.header-right {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-shrink: 0;
}

.per-page-control {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
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

@media (max-width: 768px) {
  .universe-tabs {
    max-width: 100%;
  }
}

/* Bypass button styles */
.btn-bypass-active {
  background: var(--indicator-remote) !important;
  color: white !important;
  animation: pulse-bypass 1.5s infinite;
}

@keyframes pulse-bypass {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}

/* Park mode active button */
.btn-park-active {
  background: #f59e0b !important;
  color: #000 !important;
  font-weight: bold;
  animation: pulse-park 1.5s infinite;
}

@keyframes pulse-park {
  0%, 100% { opacity: 1; box-shadow: 0 0 8px #f59e0b; }
  50% { opacity: 0.85; box-shadow: 0 0 4px #f59e0b; }
}

/* Highlight mode active button */
.btn-highlight-active {
  background: #06b6d4 !important;
  color: #000 !important;
  font-weight: bold;
  animation: pulse-highlight 1.5s infinite;
}

@keyframes pulse-highlight {
  0%, 100% { opacity: 1; box-shadow: 0 0 8px #06b6d4; }
  50% { opacity: 0.85; box-shadow: 0 0 4px #06b6d4; }
}

/* Non-clickable status indicator (no permission) */
.btn-no-click {
  cursor: not-allowed !important;
  opacity: 0.8;
}

/* Master Fader Styles */
.master-fader {
  border: 2px solid var(--border);
  background: var(--bg-tertiary);
}

.master-fader .master-label {
  font-weight: bold;
  font-size: 14px;
  color: var(--text-primary);
}

.master-fader .fader-name {
  font-size: 9px;
  color: var(--text-secondary);
}

.master-fader .master-track {
  background: var(--bg-primary);
}

/* Universe Master - uses dynamic color from store */
.universe-master {
  /* border-color is set via inline style */
}

/* Global Master - uses dynamic color from store */
.global-master {
  /* border-color is set via inline style */
}

/* Fader Footer with Park/Highlight buttons */
.fader-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  width: 100%;
  margin-top: 2px;
}

.fader-footer .fader-value {
  flex: 1;
  text-align: center;
  min-width: 28px;
}

.park-btn, .highlight-btn {
  width: 18px;
  height: 18px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 3px;
  font-size: 9px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  user-select: none;
  -webkit-user-select: none;
  touch-action: manipulation;
}

.park-btn:hover, .highlight-btn:hover {
  border-color: var(--text-secondary);
}

.park-btn:active, .highlight-btn:active {
  transform: scale(0.95);
}

/* Park button active state - orange/amber */
.park-btn.active {
  background: #f59e0b;
  border-color: #f59e0b;
  color: #000;
}

/* Highlight button active state - cyan/blue */
.highlight-btn.active {
  background: #06b6d4;
  border-color: #06b6d4;
  color: #000;
}
</style>

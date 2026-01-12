<template>
  <div>
    <div class="fader-header">
      <div class="header-top">
        <h2 class="card-title">Fader Control</h2>
        <div class="header-right">
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
          <span class="fader-value">
            <span class="fader-percent">{{ Math.round(displayValues[channel - 1] / 255 * 100) }}%</span>
            <span class="fader-raw">{{ displayValues[channel - 1] }}</span>
          </span>
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
      </div>
    </div>

    <!-- Quick actions -->
    <div class="card" style="margin-top: 16px; padding: 12px;">
      <div style="display: flex; gap: 8px; flex-wrap: wrap;">
        <button class="btn btn-secondary" @click="setAllVisible(255)">All Full</button>
        <button class="btn btn-secondary" @click="setAllVisible(0)">All Zero</button>
        <button class="btn btn-secondary" @click="setAllVisible(128)">All 50%</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useDmxStore } from '../stores/dmx.js'
import { wsManager } from '../websocket.js'

const dmxStore = useDmxStore()

const values = ref(new Array(512).fill(0))
const inputValues = ref(new Array(512).fill(0))
const currentRange = ref({ start: 1, end: 64 })
const dragging = ref(null)
const channelsPerPage = ref(parseInt(localStorage.getItem('dmxx_channelsPerPage')) || 64)
const remoteActiveChannels = ref({})  // { channel: true } for blue light indicator
const localActiveChannels = ref({})   // { channel: timeoutId } for yellow light fade
const groupActiveChannels = ref({})   // { channel: timeoutId } for green light fade (group control)
const lastInputValues = ref(new Array(512).fill(0))  // Track last input values to detect changes
let pendingRemoteIndicatorClear = null  // Single timeout for clearing remote indicators
let lastRemoteChangedChannels = []  // Channels from last input update
let activeSceneClearTimeout = null  // Debounce active scene clear to avoid flooding WebSocket
const showUniverseJump = ref(false)
const pendingChannelUpdates = ref({})  // Debounce buffer for channel updates
let channelUpdateTimeout = null

const channelRanges = computed(() => {
  const ranges = []
  for (let start = 1; start <= 512; start += channelsPerPage.value) {
    const end = Math.min(start + channelsPerPage.value - 1, 512)
    ranges.push({ start, end })
  }
  return ranges
})

watch(channelsPerPage, (newVal) => {
  if (newVal < 1) channelsPerPage.value = 1
  else if (newVal > 512) channelsPerPage.value = 512
  localStorage.setItem('dmxx_channelsPerPage', channelsPerPage.value.toString())
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
  // Show raw local values - backend handles HTP/LTP merging for output
  return values.value
})

onMounted(async () => {
  await dmxStore.loadChannelLabels(dmxStore.currentUniverse)
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

function handleChannelChange(data) {
  if (data.universe_id === dmxStore.currentUniverse) {
    values.value[data.channel - 1] = data.value
    const channel = data.channel

    // Set timeout for appropriate indicator based on source
    if (data.source === 'group') {
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

    // Find changed channels and update only those values (more efficient than array replacement)
    for (let i = 0; i < newValues.length; i++) {
      if (newValues[i] !== lastInputValues.value[i]) {
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

    lastInputValues.value = [...newValues]
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

function startDrag(event, channel) {
  event.preventDefault()
  dragging.value = { channel, element: event.target.closest('.fader-track') }
  handleDrag(event)
}

function handleDrag(event) {
  if (!dragging.value) return

  // Prevent page scroll while dragging fader
  event.preventDefault()

  const { channel, element } = dragging.value
  const rect = element.getBoundingClientRect()
  const clientY = event.touches ? event.touches[0].clientY : event.clientY
  const y = rect.bottom - clientY
  const height = rect.height
  const value = Math.round(Math.max(0, Math.min(255, (y / height) * 255)))

  setChannel(channel, value)
}

function stopDrag() {
  dragging.value = null
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
</style>

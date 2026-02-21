<template>
  <div>
    <div class="card-header" style="margin-bottom: 16px;">
      <h2 class="card-title">Network Monitor</h2>
      <div class="header-buttons">
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
          :title="authStore.canHighlight ? 'Click to exit highlight mode' : 'Highlight mode active (no permission to change)'"
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
      </div>
    </div>

    <!-- Tab Bar -->
    <div class="monitor-tabs">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'input' }"
        @click="activeTab = 'input'"
      >
        Input Monitor
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'output' }"
        @click="activeTab = 'output'"
      >
        Output Monitor
      </button>
    </div>

    <!-- ==================== INPUT TAB ==================== -->
    <div v-if="activeTab === 'input'">
      <div class="tab-header">
        <span class="source-count">{{ Object.keys(sources).length }} sources detected</span>
        <button
          class="btn btn-small"
          :class="isRunning ? 'btn-danger' : 'btn-primary'"
          @click="toggleMonitor"
          :disabled="loading"
        >
          {{ isRunning ? 'Stop Monitor' : 'Start Monitor' }}
        </button>
      </div>

    <!-- Info Banner -->
    <div class="info-banner">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <span>Passively monitors all Art-Net (port 6454) and sACN (port 5568) traffic on the network. Click a source to view all 512 channel values.</span>
    </div>

    <!-- Stats Row -->
    <div v-if="isRunning" class="stats-row">
      <div class="stat-card">
        <span class="stat-value">{{ stats.total_sources || 0 }}</span>
        <span class="stat-label">Total Sources</span>
      </div>
      <div class="stat-card">
        <span class="stat-value active">{{ stats.active_sources || 0 }}</span>
        <span class="stat-label">Active</span>
      </div>
      <div class="stat-card">
        <span class="stat-value artnet">{{ stats.artnet_sources || 0 }}</span>
        <span class="stat-label">Art-Net</span>
      </div>
      <div class="stat-card">
        <span class="stat-value sacn">{{ stats.sacn_sources || 0 }}</span>
        <span class="stat-label">sACN</span>
      </div>
      <div class="stat-card">
        <span class="stat-value">{{ stats.total_packets || 0 }}</span>
        <span class="stat-label">Total Packets</span>
      </div>
    </div>

    <!-- Not Running State -->
    <div v-if="!isRunning" class="not-running-card">
      <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"></circle>
        <polygon points="10 8 16 12 10 16 10 8"></polygon>
      </svg>
      <h3>Monitor Stopped</h3>
      <p>Click "Start Monitor" to begin detecting Art-Net and sACN traffic on your network.</p>
    </div>

    <!-- Sources Grid -->
    <div v-if="isRunning" class="sources-grid">
      <div
        v-for="(source, key) in sortedSources"
        :key="key"
        class="source-card"
        :class="{
          active: source.is_active,
          inactive: !source.is_active,
          selected: selectedSource === key
        }"
        @click="selectSource(key)"
      >
        <div class="source-header">
          <span class="protocol-badge" :class="source.protocol">
            {{ source.protocol === 'artnet' ? 'Art-Net' : 'sACN' }}
          </span>
          <span class="universe-badge">Universe {{ source.universe }}</span>
          <span class="status-dot" :class="{ active: source.is_active }"></span>
        </div>
        <div class="source-ip">{{ source.ip }}</div>
        <div class="source-stats">
          <div class="stat">
            <span class="stat-value">{{ source.packets_per_second?.toFixed(1) || '0.0' }}</span>
            <span class="stat-label">pkt/s</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ source.changing_channels?.length || 0 }}</span>
            <span class="stat-label">changing</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ source.packet_count || 0 }}</span>
            <span class="stat-label">total</span>
          </div>
        </div>

        <!-- Mini activity bar -->
        <div class="activity-bar">
          <div
            v-for="ch in 32"
            :key="ch"
            class="activity-cell"
            :class="{ active: isChannelActive(source, ch) }"
            :style="getActivityCellStyle(source, ch)"
          ></div>
        </div>
      </div>
    </div>

    <div v-if="isRunning && Object.keys(sources).length === 0" class="no-sources">
      <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="12" cy="12" r="10"></circle>
        <path d="M12 6v6l4 2"></path>
      </svg>
      <p>Waiting for DMX traffic...</p>
      <p class="hint">Send Art-Net or sACN data to this machine to see it appear here.</p>
    </div>

    <!-- Selected Source Detail Panel -->
    <div v-if="selectedSource && sources[selectedSource]" class="source-detail">
      <div class="detail-header">
        <div class="detail-title">
          <span class="protocol-badge large" :class="sources[selectedSource].protocol">
            {{ sources[selectedSource].protocol === 'artnet' ? 'Art-Net' : 'sACN' }}
          </span>
          <h3>{{ sources[selectedSource].ip }} - Universe {{ sources[selectedSource].universe }}</h3>
        </div>
        <button class="btn btn-small btn-secondary" @click="selectedSource = null">Close</button>
      </div>

      <div class="detail-stats">
        <div class="detail-stat">
          <span class="label">Packets/sec:</span>
          <span class="value">{{ sources[selectedSource].packets_per_second?.toFixed(1) || '0.0' }}</span>
        </div>
        <div class="detail-stat">
          <span class="label">Total packets:</span>
          <span class="value">{{ sources[selectedSource].packet_count || 0 }}</span>
        </div>
        <div class="detail-stat">
          <span class="label">Changing channels:</span>
          <span class="value changing">{{ sources[selectedSource].changing_channels?.join(', ') || 'None' }}</span>
        </div>
      </div>

      <!-- Channel Grid -->
      <div class="channel-grid-container">
        <div class="channel-grid">
          <div
            v-for="channel in 512"
            :key="channel"
            class="channel-cell"
            :class="{
              active: selectedSourceValues[channel - 1] > 0,
              changing: isChannelChanging(channel)
            }"
            :style="getChannelCellStyle(channel)"
          >
            <span class="channel-num">{{ channel }}</span>
            <span class="channel-value">{{ selectedSourceValues[channel - 1] || 0 }} | {{ Math.round((selectedSourceValues[channel - 1] || 0) / 255 * 100) }}%</span>
          </div>
        </div>
      </div>
    </div>
    </div>

    <!-- ==================== OUTPUT TAB ==================== -->
    <div v-if="activeTab === 'output'" class="output-monitor">
      <div class="tab-header">
        <div class="universe-selector">
          <label>Universe:</label>
          <select v-model="outputUniverse">
            <option v-for="uid in availableUniverses" :key="uid" :value="uid">{{ uid }}</option>
          </select>
        </div>
      </div>

      <div class="info-banner">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <line x1="12" y1="16" x2="12" y2="12"></line>
          <line x1="12" y1="8" x2="12.01" y2="8"></line>
        </svg>
        <span>Shows the actual DMX values being sent to outputs after all processing (merge, mapping, groups, grandmaster scaling).</span>
      </div>

      <!-- Grandmaster Display -->
      <div class="grandmaster-display">
        <div class="gm-item">
          <span class="gm-label">Global Master:</span>
          <span class="gm-value">{{ globalGrandmaster }} ({{ Math.round(globalGrandmaster / 255 * 100) }}%)</span>
        </div>
        <div class="gm-item">
          <span class="gm-label">Universe Master:</span>
          <span class="gm-value">{{ universeGrandmaster }} ({{ Math.round(universeGrandmaster / 255 * 100) }}%)</span>
        </div>
      </div>

      <!-- Output Channel Grid -->
      <div class="source-detail">
        <div class="detail-header">
          <div class="detail-title">
            <span class="protocol-badge large output">OUTPUT</span>
            <h3>Universe {{ outputUniverse }} - Final DMX Values</h3>
          </div>
        </div>

        <div class="channel-grid-container">
          <div class="channel-grid">
            <div
              v-for="channel in 512"
              :key="channel"
              class="channel-cell"
              :class="{ active: outputValues[channel - 1] > 0 }"
              :style="getOutputCellStyle(channel)"
            >
              <span class="channel-num">{{ channel }}</span>
              <span class="channel-value">{{ outputValues[channel - 1] || 0 }} | {{ Math.round((outputValues[channel - 1] || 0) / 255 * 100) }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, onBeforeUnmount, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useDmxStore } from '../stores/dmx.js'

const authStore = useAuthStore()
const dmxStore = useDmxStore()

// Tab state
const activeTab = ref('input')

// Input monitor state
const isRunning = ref(false)
const loading = ref(false)
const sources = reactive({})
const selectedSource = ref(null)
const selectedSourceValues = ref(new Array(512).fill(0))
const stats = ref({})
let ws = null
let reconnectTimeout = null

// Output monitor state
const outputUniverse = ref(1)
const outputValues = ref(new Array(512).fill(0))
const availableUniverses = ref([1])
const globalGrandmaster = ref(255)
const universeGrandmaster = ref(255)
let outputPollInterval = null

// Computed: sources sorted by packet rate (most active first)
const sortedSources = computed(() => {
  return Object.entries(sources)
    .sort((a, b) => {
      // Active sources first
      if (a[1].is_active !== b[1].is_active) {
        return b[1].is_active ? 1 : -1
      }
      // Then by packets per second
      return (b[1].packets_per_second || 0) - (a[1].packets_per_second || 0)
    })
    .reduce((acc, [key, value]) => {
      acc[key] = value
      return acc
    }, {})
})

// Computed: check if any channels are parked
const hasParkedChannels = computed(() => {
  return dmxStore.parkedChannels && Object.keys(dmxStore.parkedChannels).length > 0
})

// Toggle input bypass
function toggleBypass() {
  if (dmxStore.inputBypassActive) {
    dmxStore.stopBypass()
  } else {
    dmxStore.startBypass()
  }
}

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

async function loadStatus() {
  try {
    const response = await fetchWithAuth('/api/monitor')
    const data = await response.json()
    isRunning.value = data.running
    stats.value = data.stats || {}

    // Load existing sources (clear old ones first)
    Object.keys(sources).forEach(key => delete sources[key])
    if (data.sources) {
      Object.assign(sources, data.sources)
    }

    // Connect WebSocket if monitor is running
    if (isRunning.value) {
      connectWebSocket()
    }
  } catch (e) {
    console.error('Failed to load monitor status:', e)
  }
}

async function toggleMonitor() {
  loading.value = true
  try {
    const endpoint = isRunning.value ? '/api/monitor/stop' : '/api/monitor/start'
    const response = await fetchWithAuth(endpoint, { method: 'POST' })
    const data = await response.json()
    isRunning.value = data.running

    if (isRunning.value) {
      connectWebSocket()
    } else {
      disconnectWebSocket()
      // Clear sources when stopped
      Object.keys(sources).forEach(key => delete sources[key])
      selectedSource.value = null
    }
  } catch (e) {
    console.error('Failed to toggle monitor:', e)
  } finally {
    loading.value = false
  }
}

function connectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  ws = new WebSocket(`${protocol}//${window.location.host}/api/monitor/ws`)

  ws.onopen = () => {
  }

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data)
    handleMessage(message)
  }

  ws.onclose = () => {
    if (isRunning.value) {
      // Reconnect after a delay
      reconnectTimeout = setTimeout(connectWebSocket, 2000)
    }
  }

  ws.onerror = (error) => {
    console.error('Monitor WebSocket error:', error)
  }
}

function disconnectWebSocket() {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout)
    reconnectTimeout = null
  }
  if (ws) {
    ws.close()
    ws = null
  }
}

function handleMessage(message) {
  switch (message.type) {
    case 'monitor_status':
      isRunning.value = message.data.running
      if (message.data.sources) {
        Object.keys(sources).forEach(key => delete sources[key])
        Object.assign(sources, message.data.sources)
      }
      break

    case 'monitor_source_new':
      sources[message.data.key] = {
        ...message.data,
        is_active: true,
        changing_channels: [],
        packet_count: 0,
        packets_per_second: 0
      }
      break

    case 'monitor_update':
      for (const [key, update] of Object.entries(message.data.sources)) {
        if (sources[key]) {
          Object.assign(sources[key], update)
          sources[key].is_active = true
        }
      }
      // Update stats
      stats.value = {
        total_sources: Object.keys(sources).length,
        active_sources: Object.values(sources).filter(s => s.is_active).length,
        artnet_sources: Object.values(sources).filter(s => s.protocol === 'artnet').length,
        sacn_sources: Object.values(sources).filter(s => s.protocol === 'sacn').length,
        total_packets: Object.values(sources).reduce((sum, s) => sum + (s.packet_count || 0), 0)
      }
      break

    case 'monitor_source_timeout':
      if (sources[message.data.key]) {
        sources[message.data.key].is_active = false
      }
      break

    case 'monitor_source_removed':
      delete sources[message.data.key]
      if (selectedSource.value === message.data.key) {
        selectedSource.value = null
      }
      break

    case 'monitor_source_values':
      if (message.data.key === selectedSource.value) {
        selectedSourceValues.value = message.data.values
      }
      break
  }
}

function selectSource(key) {
  if (selectedSource.value === key) {
    selectedSource.value = null
    return
  }

  selectedSource.value = key
  selectedSourceValues.value = new Array(512).fill(0)

  // Subscribe to full value updates
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: 'subscribe_source',
      source_key: key
    }))
  }
}

function isChannelActive(source, channelGroup) {
  // Check if any channel in this group (16 channels per cell for mini bar) has activity
  const startChannel = (channelGroup - 1) * 16 + 1
  const endChannel = startChannel + 15
  const changing = source.changing_channels || []
  return changing.some(ch => ch >= startChannel && ch <= endChannel)
}

function getActivityCellStyle(source, channelGroup) {
  if (isChannelActive(source, channelGroup)) {
    return { background: 'var(--success)' }
  }
  return {}
}

function isChannelChanging(channel) {
  if (!selectedSource.value || !sources[selectedSource.value]) return false
  const changing = sources[selectedSource.value].changing_channels || []
  return changing.includes(channel)
}

function getChannelCellStyle(channel) {
  const value = selectedSourceValues.value[channel - 1] || 0
  const intensity = value / 255
  const isChanging = isChannelChanging(channel)

  if (value > 0) {
    return {
      background: `rgba(74, 222, 128, ${0.2 + intensity * 0.6})`,
      borderColor: isChanging ? 'var(--accent)' : 'transparent'
    }
  }
  return {
    borderColor: isChanging ? 'var(--accent)' : 'transparent'
  }
}

// Output Monitor Functions
function getOutputCellStyle(channel) {
  const value = outputValues.value[channel - 1] || 0
  const intensity = value / 255

  if (value > 0) {
    return {
      background: `rgba(59, 130, 246, ${0.2 + intensity * 0.6})`
    }
  }
  return {}
}

async function loadUniverses() {
  try {
    const response = await fetchWithAuth('/api/universes')
    const data = await response.json()
    if (data.universes && data.universes.length > 0) {
      availableUniverses.value = data.universes.map(u => u.id)
      if (!availableUniverses.value.includes(outputUniverse.value)) {
        outputUniverse.value = availableUniverses.value[0]
      }
    }
  } catch (e) {
    console.error('Failed to load universes:', e)
  }
}

async function loadOutputValues() {
  if (activeTab.value !== 'output') return

  try {
    const response = await fetchWithAuth(`/api/dmx/values/${outputUniverse.value}`)
    const data = await response.json()
    if (data.values) {
      outputValues.value = data.values
    }
    if (data.global_grandmaster !== undefined) {
      globalGrandmaster.value = data.global_grandmaster
    }
    if (data.universe_grandmaster !== undefined) {
      universeGrandmaster.value = data.universe_grandmaster
    }
  } catch (e) {
    console.error('Failed to load output values:', e)
  }
}

function startOutputPolling() {
  if (outputPollInterval) return
  loadOutputValues()
  outputPollInterval = setInterval(loadOutputValues, 100)
}

function stopOutputPolling() {
  if (outputPollInterval) {
    clearInterval(outputPollInterval)
    outputPollInterval = null
  }
}

// Watch for tab changes
watch(activeTab, (newTab) => {
  if (newTab === 'output') {
    loadUniverses()
    startOutputPolling()
  } else {
    stopOutputPolling()
  }
})

watch(outputUniverse, () => {
  loadOutputValues()
})

// Warn user if monitor is still running when leaving
onBeforeRouteLeave((to, from, next) => {
  if (isRunning.value) {
    const answer = window.confirm(
      'The network monitor is still running. It will continue to use system resources in the background.\n\nDo you want to stop the monitor before leaving?'
    )
    if (answer) {
      // User wants to stop - stop and then navigate
      fetchWithAuth('/api/monitor/stop', { method: 'POST' })
        .then(() => {
          isRunning.value = false
          disconnectWebSocket()
          next()
        })
        .catch(() => next())
    } else {
      // User doesn't want to stop - just navigate
      next()
    }
  } else {
    next()
  }
})

onMounted(() => {
  loadStatus()  // Handles WebSocket connection internally after fetching status
  loadUniverses()
  if (activeTab.value === 'output') {
    startOutputPolling()
  }
})

onUnmounted(() => {
  disconnectWebSocket()
  stopOutputPolling()
})
</script>

<style scoped>
.monitor-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px;
}

.tab-btn {
  flex: 1;
  padding: 10px 20px;
  background: transparent;
  border: none;
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--bg-tertiary);
}

.tab-btn.active {
  background: var(--accent);
  color: white;
}

.tab-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.universe-selector {
  display: flex;
  align-items: center;
  gap: 8px;
}

.universe-selector label {
  font-size: 14px;
  color: var(--text-secondary);
}

.universe-selector select {
  padding: 6px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 14px;
}

.protocol-badge.output {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.output-monitor .source-detail {
  margin-top: 0;
}

.grandmaster-display {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.gm-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gm-label {
  font-size: 13px;
  color: var(--text-secondary);
}

.gm-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
  font-family: monospace;
}

.monitor-header-controls {
  display: flex;
  align-items: center;
  gap: 16px;
}

.source-count {
  font-size: 13px;
  color: var(--text-secondary);
}

.info-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.info-banner svg {
  flex-shrink: 0;
  color: var(--accent);
}

.stats-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.stat-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 100px;
}

.stat-card .stat-value {
  font-size: 24px;
  font-weight: 600;
  color: var(--text-primary);
}

.stat-card .stat-value.active {
  color: var(--success);
}

.stat-card .stat-value.artnet {
  color: #3b82f6;
}

.stat-card .stat-value.sacn {
  color: #10b981;
}

.stat-card .stat-label {
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.not-running-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 60px 40px;
  text-align: center;
  color: var(--text-secondary);
}

.not-running-card svg {
  margin-bottom: 16px;
  opacity: 0.5;
}

.not-running-card h3 {
  margin: 0 0 8px 0;
  color: var(--text-primary);
}

.not-running-card p {
  margin: 0;
  font-size: 14px;
}

.sources-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.source-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s;
}

.source-card:hover {
  border-color: var(--accent);
}

.source-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.source-card.inactive {
  opacity: 0.5;
}

.source-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.protocol-badge {
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}

.protocol-badge.artnet {
  background: rgba(59, 130, 246, 0.2);
  color: #3b82f6;
}

.protocol-badge.sacn {
  background: rgba(16, 185, 129, 0.2);
  color: #10b981;
}

.protocol-badge.large {
  padding: 4px 12px;
  font-size: 12px;
}

.universe-badge {
  font-size: 12px;
  color: var(--text-secondary);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
  margin-left: auto;
}

.status-dot.active {
  background: var(--success);
  box-shadow: 0 0 6px var(--success);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.source-ip {
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 10px;
  font-family: monospace;
}

.source-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 10px;
}

.source-stats .stat {
  display: flex;
  flex-direction: column;
}

.source-stats .stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
}

.source-stats .stat-label {
  font-size: 10px;
  color: var(--text-secondary);
}

.activity-bar {
  display: flex;
  gap: 2px;
  height: 6px;
}

.activity-cell {
  flex: 1;
  background: var(--bg-tertiary);
  border-radius: 1px;
  transition: background 0.1s;
}

.activity-cell.active {
  background: var(--success);
}

.no-sources {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 40px;
  text-align: center;
  color: var(--text-secondary);
}

.no-sources svg {
  margin-bottom: 12px;
  opacity: 0.5;
}

.no-sources p {
  margin: 0 0 8px 0;
}

.no-sources .hint {
  font-size: 12px;
  opacity: 0.7;
}

.source-detail {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.detail-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.detail-title h3 {
  margin: 0;
  font-size: 16px;
  font-family: monospace;
}

.detail-stats {
  display: flex;
  gap: 24px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.detail-stat {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.detail-stat .label {
  color: var(--text-secondary);
}

.detail-stat .value {
  font-weight: 500;
}

.detail-stat .value.changing {
  color: var(--accent);
  font-family: monospace;
  font-size: 12px;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.channel-grid-container {
  background: var(--bg-tertiary);
  border-radius: 6px;
  padding: 8px;
}

.channel-grid {
  display: grid;
  grid-template-columns: repeat(32, 1fr);
  gap: 2px;
}

.channel-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4px 4px;
  background: var(--bg-secondary);
  border: 1px solid transparent;
  border-radius: 2px;
  min-width: 52px;
  transition: all 0.1s;
}

.channel-cell.active {
  color: white;
}

.channel-cell.changing {
  border-color: var(--accent);
  animation: highlight 0.5s ease;
}

@keyframes highlight {
  0% { transform: scale(1.1); }
  100% { transform: scale(1); }
}

.channel-num {
  font-size: 8px;
  opacity: 0.6;
  line-height: 1;
}

.channel-value {
  font-size: 8px;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
}

@media (max-width: 1400px) {
  .channel-grid {
    grid-template-columns: repeat(24, 1fr);
  }
}

@media (max-width: 1000px) {
  .channel-grid {
    grid-template-columns: repeat(16, 1fr);
  }
}

@media (max-width: 700px) {
  .channel-grid {
    grid-template-columns: repeat(8, 1fr);
  }
  .channel-value {
    font-size: 10px;
  }
}

/* Header buttons */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* Status button styles */
.btn-park-active {
  background: #f59e0b !important;
  color: #000 !important;
  font-weight: bold;
  animation: pulse-park 1.5s infinite;
}

.btn-highlight-active {
  background: #3b82f6 !important;
  color: #fff !important;
  font-weight: bold;
  animation: pulse-highlight 1.5s infinite;
}

.btn-bypass-active {
  background: #ef4444 !important;
  color: #fff !important;
  font-weight: bold;
  animation: pulse-bypass 1.5s infinite;
}

@keyframes pulse-park {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(245, 158, 11, 0); }
}

@keyframes pulse-highlight {
  0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(59, 130, 246, 0); }
}

@keyframes pulse-bypass {
  0%, 100% { box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
  50% { box-shadow: 0 0 0 4px rgba(239, 68, 68, 0); }
}

/* Non-clickable status indicator (no permission) */
.btn-no-click {
  cursor: not-allowed !important;
  opacity: 0.8;
}
</style>

<template>
  <div class="midi-control">
    <div class="header">
      <h1>MIDI Control</h1>
      <div class="header-actions">
        <router-link to="/io" class="btn btn-secondary">Back to I/O</router-link>
      </div>
    </div>

    <!-- Status Card -->
    <div class="card status-card">
      <h2>MIDI Status</h2>
      <div class="status-grid">
        <div class="status-item">
          <span class="label">MIDI Support:</span>
          <span :class="['status-badge', status.available ? 'success' : 'error']">
            {{ status.available ? 'Available' : 'Not Available' }}
          </span>
        </div>
        <div class="status-item">
          <span class="label">Input:</span>
          <span v-if="connectedDevices.length > 0" class="status-badge success">
            {{ connectedDevices.length }} device(s)
          </span>
          <span v-else class="status-badge inactive">Disconnected</span>
        </div>
        <div class="status-item">
          <span class="label">Output:</span>
          <span :class="['status-badge', status.output?.running ? 'success' : 'inactive']">
            {{ status.output?.running ? status.output.device : 'Disconnected' }}
          </span>
        </div>
        <div class="status-item" v-if="status.input?.running">
          <span class="label">Messages Received:</span>
          <span>{{ status.input?.messages_received || 0 }}</span>
        </div>
      </div>
    </div>

    <!-- Device Connection Card (Multi-Device Support) -->
    <div class="card">
      <h2>Device Connection</h2>
      <p class="section-hint">Connect multiple MIDI devices simultaneously. Each device can have separate mappings.</p>
      <div class="connection-section">
        <div class="device-list">
          <h3>Input Devices</h3>
          <div v-if="devices.inputs.length === 0" class="empty-state">
            <p>No MIDI input devices found.</p>
          </div>
          <div v-else class="device-grid">
            <div v-for="device in devices.inputs" :key="device" class="device-item">
              <span class="device-name" :class="{ connected: isDeviceConnected(device) }">{{ device }}</span>
              <button
                v-if="!isDeviceConnected(device)"
                class="btn btn-small btn-primary"
                @click="connectDevice(device)"
              >
                Connect
              </button>
              <button
                v-else
                class="btn btn-small btn-secondary"
                @click="disconnectDevice(device)"
              >
                Disconnect
              </button>
            </div>
          </div>
        </div>
        <div class="device-list">
          <h3>Output Device</h3>
          <div class="connection-group">
            <select v-model="selectedOutputDevice" :disabled="status.output?.running">
              <option value="">-- Select Output --</option>
              <option v-for="device in devices.outputs" :key="device" :value="device">
                {{ device }}
              </option>
            </select>
            <button
              v-if="!status.output?.running"
              class="btn btn-primary"
              @click="connectOutput"
              :disabled="!selectedOutputDevice"
            >
              Connect
            </button>
            <button
              v-else
              class="btn btn-secondary"
              @click="disconnectOutput"
            >
              Disconnect
            </button>
          </div>
          <div v-if="status.output?.running" class="feedback-toggle">
            <label class="toggle">
              <input type="checkbox" :checked="feedbackEnabled" @change="toggleFeedback">
              <span class="slider"></span>
            </label>
            <span class="feedback-label">Send feedback to controller</span>
          </div>
        </div>
        <button class="btn btn-secondary" @click="refreshDevices">
          Refresh Devices
        </button>
      </div>
    </div>

    <!-- Network MIDI Card -->
    <div class="card">
      <h2>Network MIDI (rtpMIDI)</h2>
      <div class="network-section">
        <div class="network-status">
          <span class="label">Support:</span>
          <span :class="['status-badge', networkStatus.available ? 'success' : 'error']">
            {{ networkStatus.available ? 'Available' : 'Not Available (install pymidi)' }}
          </span>
        </div>

        <div v-if="networkStatus.available" class="network-controls">
          <div class="server-section">
            <h3>Server Mode</h3>
            <p class="hint">Start a server so other devices can connect to DMXX.</p>
            <div class="server-controls">
              <div class="form-inline">
                <label>Port:</label>
                <input
                  type="number"
                  v-model.number="networkPort"
                  :disabled="networkStatus.server_running"
                  min="1024"
                  max="65535"
                >
                <label>Name:</label>
                <input
                  type="text"
                  v-model="networkName"
                  :disabled="networkStatus.server_running"
                  placeholder="DMXX"
                >
              </div>
              <button
                v-if="!networkStatus.server_running"
                class="btn btn-primary"
                @click="startNetworkServer"
              >
                Start Server
              </button>
              <button
                v-else
                class="btn btn-secondary"
                @click="stopNetworkServer"
              >
                Stop Server
              </button>
            </div>
            <div v-if="networkStatus.server_running" class="server-info">
              <span :class="['status-badge', 'success']">
                Listening on port {{ networkStatus.port }}
              </span>
            </div>
          </div>

          <div v-if="networkStatus.server_running && networkStatus.peers?.length > 0" class="peers-section">
            <h3>Connected Devices</h3>
            <div class="peers-list">
              <div v-for="peer in networkStatus.peers" :key="peer.name" class="peer-item">
                <span class="peer-name">{{ peer.name }}</span>
                <span class="peer-address">{{ peer.address }}</span>
              </div>
            </div>
          </div>
          <div v-else-if="networkStatus.server_running" class="empty-peers">
            <p>No devices connected. Connect from another device using this computer's IP address and port {{ networkStatus.port }}.</p>
          </div>
        </div>
      </div>
    </div>

    <!-- CC Mappings Card (to Input Channels) -->
    <div class="card">
      <div class="card-header">
        <h2>CC Mappings (to Input Channels)</h2>
        <button class="btn btn-primary" @click="showAddCCMapping = true">+ Add CC Mapping</button>
      </div>
      <p class="section-hint">Map MIDI CC (faders/knobs) to universe channels. Set up MIDI input on the I/O page first.</p>

      <div v-if="ccMappings.length === 0" class="empty-state">
        <p>No CC mappings yet. Click + Add CC Mapping to create one.</p>
      </div>

      <div v-else class="mappings-table">
        <table>
          <thead>
            <tr>
              <th>Device</th>
              <th>CC</th>
              <th>MIDI Ch</th>
              <th>Channel</th>
              <th>Label</th>
              <th>Enabled</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="m in ccMappings" :key="m.id" :class="{ disabled: !m.enabled }">
              <td class="device-cell">{{ m.device_name || 'All' }}</td>
              <td>{{ m.cc_number }}</td>
              <td>{{ m.midi_channel === -1 ? 'All' : m.midi_channel + 1 }}</td>
              <td>{{ m.input_channel }}</td>
              <td>{{ m.label || '-' }}</td>
              <td>
                <label class="toggle">
                  <input type="checkbox" :checked="m.enabled" @change="toggleCCMapping(m)">
                  <span class="slider"></span>
                </label>
              </td>
              <td>
                <button class="btn btn-small" @click="editCCMapping(m)">Edit</button>
                <button class="btn btn-small btn-danger" @click="deleteCCMapping(m)">X</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Note Triggers Card (Direct Actions) -->
    <div class="card">
      <div class="card-header">
        <h2>Note Triggers (Direct Actions)</h2>
        <button class="btn btn-primary" @click="showAddTrigger = true">+ Add Trigger</button>
      </div>
      <p class="section-hint">Map MIDI notes (buttons) to direct actions. These bypass the mapping system.</p>

      <div v-if="triggers.length === 0" class="empty-state">
        <p>No triggers yet. Click + Add Trigger to create one.</p>
      </div>

      <div v-else class="mappings-table">
        <table>
          <thead>
            <tr>
              <th>Device</th>
              <th>Note</th>
              <th>MIDI Ch</th>
              <th>Action</th>
              <th>Target</th>
              <th>Label</th>
              <th>Enabled</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in triggers" :key="t.id" :class="{ disabled: !t.enabled }">
              <td class="device-cell">{{ t.device_name || 'All' }}</td>
              <td>{{ t.note }} ({{ noteToName(t.note) }})</td>
              <td>{{ t.midi_channel === -1 ? 'All' : t.midi_channel + 1 }}</td>
              <td>{{ t.action }}</td>
              <td>{{ t.action === 'blackout' ? '-' : '#' + t.target_id }}</td>
              <td>{{ t.label || '-' }}</td>
              <td>
                <label class="toggle">
                  <input type="checkbox" :checked="t.enabled" @change="toggleTrigger(t)">
                  <span class="slider"></span>
                </label>
              </td>
              <td>
                <button class="btn btn-small" @click="editTrigger(t)">Edit</button>
                <button class="btn btn-small btn-danger" @click="deleteTrigger(t)">X</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Add/Edit CC Mapping Modal -->
    <div v-if="showAddCCMapping || editingCCMapping" class="modal-overlay" @click.self="closeCCModal">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingCCMapping ? 'Edit' : 'New' }} CC Mapping</h3>
          <button class="modal-close" @click="closeCCModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Device</label>
          <select class="form-select" v-model="ccForm.device_name">
            <option :value="null">All Devices</option>
            <option v-for="device in connectedDevices" :key="device" :value="device">
              {{ device }}
            </option>
          </select>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">CC Number (0-127)</label>
            <div class="input-with-listen">
              <input class="form-input" type="number" v-model.number="ccForm.cc_number" min="0" max="127">
              <button
                type="button"
                :class="['btn', 'btn-small', ccModalListening ? 'btn-warning' : 'btn-secondary']"
                @click="toggleCCModalListen"
              >
                {{ ccModalListening ? 'Stop' : 'Listen' }}
              </button>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">MIDI Channel</label>
            <select class="form-select" v-model="ccForm.midi_channel">
              <option :value="-1">All Channels</option>
              <option v-for="ch in 16" :key="ch" :value="ch - 1">Channel {{ ch }}</option>
            </select>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Input Channel (1-512)</label>
          <input class="form-input" type="number" v-model.number="ccForm.input_channel" min="1" max="512">
          <p class="form-help">Applies to all universes with MIDI input enabled on the I/O page.</p>
        </div>

        <div class="form-group">
          <label class="form-label">Label (optional)</label>
          <input class="form-input" type="text" v-model="ccForm.label" placeholder="e.g., Fader 1">
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeCCModal">Cancel</button>
          <button class="btn btn-primary" @click="saveCCMapping">Save</button>
        </div>
      </div>
    </div>

    <!-- Add/Edit Trigger Modal -->
    <div v-if="showAddTrigger || editingTrigger" class="modal-overlay" @click.self="closeTriggerModal">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingTrigger ? 'Edit' : 'New' }} Trigger</h3>
          <button class="modal-close" @click="closeTriggerModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Device</label>
          <select class="form-select" v-model="triggerForm.device_name">
            <option :value="null">All Devices</option>
            <option v-for="device in connectedDevices" :key="device" :value="device">
              {{ device }}
            </option>
          </select>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Note Number (0-127)</label>
            <div class="input-with-listen">
              <input class="form-input" type="number" v-model.number="triggerForm.note" min="0" max="127">
              <button
                type="button"
                :class="['btn', 'btn-small', noteModalListening ? 'btn-warning' : 'btn-secondary']"
                @click="toggleNoteModalListen"
              >
                {{ noteModalListening ? 'Stop' : 'Listen' }}
              </button>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">MIDI Channel</label>
            <select class="form-select" v-model="triggerForm.midi_channel">
              <option :value="-1">All Channels</option>
              <option v-for="ch in 16" :key="ch" :value="ch - 1">Channel {{ ch }}</option>
            </select>
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Action</label>
            <select class="form-select" v-model="triggerForm.action">
              <option value="scene">Recall Scene</option>
              <option value="blackout">Toggle Blackout</option>
              <option value="group">Trigger Group</option>
            </select>
          </div>
          <div class="form-group" v-if="triggerForm.action !== 'blackout'">
            <label class="form-label">{{ triggerForm.action === 'scene' ? 'Scene' : 'Group' }} ID</label>
            <input class="form-input" type="number" v-model.number="triggerForm.target_id" min="1">
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Label (optional)</label>
          <input class="form-input" type="text" v-model="triggerForm.label" placeholder="e.g., Go Scene 1">
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeTriggerModal">Cancel</button>
          <button class="btn btn-primary" @click="saveTrigger">Save</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()

// Helper to fetch with auth
async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

const devices = ref({ inputs: [], outputs: [] })
const status = ref({ available: false, input: {}, output: {}, learn_mode: false, network: {} })
const ccMappings = ref([])
const triggers = ref([])
const selectedInputDevice = ref('')
const selectedOutputDevice = ref('')

// Modal states
const showAddCCMapping = ref(false)
const editingCCMapping = ref(null)
const showAddTrigger = ref(false)
const editingTrigger = ref(null)

// Modal listen modes (for in-modal learning)
const ccModalListening = ref(false)
const noteModalListening = ref(false)

// Network MIDI state
const networkStatus = ref({ available: false, server_running: false, peers: [] })
const networkPort = ref(5004)
const networkName = ref('DMXX')

// MIDI output feedback
const feedbackEnabled = ref(false)

// Form states
const ccForm = ref({
  cc_number: 0,
  midi_channel: -1,
  input_channel: 1,
  label: '',
  device_name: null  // null = all devices
})

const triggerForm = ref({
  note: 60,
  midi_channel: -1,
  action: 'scene',
  target_id: 1,
  label: '',
  device_name: null  // null = all devices
})

// Connected devices (for multi-device support)
const connectedDevices = ref([])

let statusPollInterval = null
let learnPollInterval = null

// Note name conversion
function noteToName(note) {
  const notes = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
  const octave = Math.floor(note / 12) - 1
  return notes[note % 12] + octave
}

onMounted(async () => {
  await refreshDevices()
  await loadStatus()
  await loadConnectedDevices()
  await loadCCMappings()
  await loadTriggers()
  await loadNetworkStatus()
  await loadFeedbackStatus()

  // Poll status every 2 seconds
  statusPollInterval = setInterval(() => {
    loadStatus()
    loadConnectedDevices()
    loadNetworkStatus()
  }, 2000)
})

onUnmounted(() => {
  if (statusPollInterval) clearInterval(statusPollInterval)
  if (learnPollInterval) clearInterval(learnPollInterval)
})

async function refreshDevices() {
  try {
    const response = await fetchWithAuth('/api/midi/devices')
    devices.value = await response.json()
  } catch (e) {
    console.error('Failed to load MIDI devices:', e)
  }
}

async function loadStatus() {
  try {
    const response = await fetchWithAuth('/api/midi/status')
    status.value = await response.json()
  } catch (e) {
    console.error('Failed to load MIDI status:', e)
  }
}

async function loadCCMappings() {
  try {
    const response = await fetchWithAuth('/api/midi/cc-mappings')
    ccMappings.value = await response.json()
  } catch (e) {
    console.error('Failed to load CC mappings:', e)
  }
}

async function loadTriggers() {
  try {
    const response = await fetchWithAuth('/api/midi/triggers')
    triggers.value = await response.json()
  } catch (e) {
    console.error('Failed to load triggers:', e)
  }
}

async function connectInput() {
  try {
    await fetchWithAuth('/api/midi/input/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_name: selectedInputDevice.value })
    })
    // Enable MIDI input integration
    await fetchWithAuth('/api/midi/input/enable', { method: 'POST' })
    await loadStatus()
  } catch (e) {
    console.error('Failed to connect MIDI input:', e)
    alert('Failed to connect MIDI input')
  }
}

async function disconnectInput() {
  try {
    await fetchWithAuth('/api/midi/input/stop', { method: 'POST' })
    await fetchWithAuth('/api/midi/input/disable', { method: 'POST' })
    await loadStatus()
  } catch (e) {
    console.error('Failed to disconnect MIDI input:', e)
  }
}

async function connectOutput() {
  try {
    await fetchWithAuth('/api/midi/output/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_name: selectedOutputDevice.value })
    })
    await loadStatus()
  } catch (e) {
    console.error('Failed to connect MIDI output:', e)
    alert('Failed to connect MIDI output')
  }
}

async function disconnectOutput() {
  try {
    await fetchWithAuth('/api/midi/output/stop', { method: 'POST' })
    await loadStatus()
    feedbackEnabled.value = false
  } catch (e) {
    console.error('Failed to disconnect MIDI output:', e)
  }
}

async function loadFeedbackStatus() {
  try {
    const response = await fetchWithAuth('/api/midi/output/feedback/status')
    const data = await response.json()
    feedbackEnabled.value = data.enabled || false
  } catch (e) {
    console.error('Failed to load feedback status:', e)
  }
}

async function toggleFeedback() {
  try {
    const endpoint = feedbackEnabled.value ? 'disable' : 'enable'
    await fetchWithAuth(`/api/midi/output/feedback/${endpoint}`, { method: 'POST' })
    feedbackEnabled.value = !feedbackEnabled.value
  } catch (e) {
    console.error('Failed to toggle feedback:', e)
  }
}

// Multi-device functions
async function loadConnectedDevices() {
  try {
    const response = await fetchWithAuth('/api/midi/input/connected-devices')
    const data = await response.json()
    connectedDevices.value = data.all_devices || []
  } catch (e) {
    console.error('Failed to load connected devices:', e)
  }
}

function isDeviceConnected(deviceName) {
  return connectedDevices.value.includes(deviceName)
}

async function connectDevice(deviceName) {
  try {
    await fetchWithAuth('/api/midi/input/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_name: deviceName })
    })
    await loadConnectedDevices()
    await loadStatus()
  } catch (e) {
    console.error('Failed to connect device:', e)
    alert('Failed to connect device: ' + deviceName)
  }
}

async function disconnectDevice(deviceName) {
  try {
    await fetchWithAuth('/api/midi/input/disconnect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_name: deviceName })
    })
    await loadConnectedDevices()
    await loadStatus()
  } catch (e) {
    console.error('Failed to disconnect device:', e)
  }
}

// Network MIDI functions
async function loadNetworkStatus() {
  try {
    const response = await fetchWithAuth('/api/midi/network/status')
    networkStatus.value = await response.json()
  } catch (e) {
    console.error('Failed to load network MIDI status:', e)
  }
}

async function startNetworkServer() {
  try {
    await fetchWithAuth('/api/midi/network/server/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        port: networkPort.value,
        name: networkName.value || 'DMXX'
      })
    })
    // Enable MIDI input integration
    await fetchWithAuth('/api/midi/input/enable', { method: 'POST' })
    await loadNetworkStatus()
  } catch (e) {
    console.error('Failed to start network MIDI server:', e)
    alert('Failed to start network MIDI server. Port may be in use.')
  }
}

async function stopNetworkServer() {
  try {
    await fetchWithAuth('/api/midi/network/server/stop', { method: 'POST' })
    await loadNetworkStatus()
  } catch (e) {
    console.error('Failed to stop network MIDI server:', e)
  }
}

function stopLearnPolling() {
  if (learnPollInterval) {
    clearInterval(learnPollInterval)
    learnPollInterval = null
  }
}

// Modal listen mode functions (for in-modal learning)
async function toggleCCModalListen() {
  try {
    if (ccModalListening.value) {
      await fetchWithAuth('/api/midi/learn/stop', { method: 'POST' })
      stopLearnPolling()
      ccModalListening.value = false
    } else {
      await fetchWithAuth('/api/midi/learn/start', { method: 'POST' })
      startModalLearnPolling('cc')
      ccModalListening.value = true
    }
  } catch (e) {
    console.error('Failed to toggle CC modal listen:', e)
  }
}

async function toggleNoteModalListen() {
  try {
    if (noteModalListening.value) {
      await fetchWithAuth('/api/midi/learn/stop', { method: 'POST' })
      stopLearnPolling()
      noteModalListening.value = false
    } else {
      await fetchWithAuth('/api/midi/learn/start', { method: 'POST' })
      startModalLearnPolling('note')
      noteModalListening.value = true
    }
  } catch (e) {
    console.error('Failed to toggle note modal listen:', e)
  }
}

function startModalLearnPolling(type) {
  if (learnPollInterval) return
  learnPollInterval = setInterval(async () => {
    try {
      const response = await fetchWithAuth('/api/midi/learn/last')
      const data = await response.json()
      if (data.message) {
        if (type === 'cc' && data.message.type === 'control_change') {
          // Auto-fill CC form
          ccForm.value.cc_number = data.message.control
          ccForm.value.midi_channel = data.message.channel
          ccForm.value.device_name = data.message.device_name || null
          toggleCCModalListen() // Stop listening
        } else if (type === 'note' && data.message.type === 'note_on') {
          // Auto-fill Trigger form
          triggerForm.value.note = data.message.note
          triggerForm.value.midi_channel = data.message.channel
          triggerForm.value.device_name = data.message.device_name || null
          toggleNoteModalListen() // Stop listening
        }
      }
    } catch (e) {
      console.error('Modal learn poll error:', e)
    }
  }, 100)
}

// CC Mapping CRUD
function closeCCModal() {
  // Stop listening if active
  if (ccModalListening.value) {
    toggleCCModalListen()
  }
  showAddCCMapping.value = false
  editingCCMapping.value = null
  ccForm.value = { cc_number: 0, midi_channel: -1, input_channel: 1, label: '', device_name: null }
}

function editCCMapping(m) {
  editingCCMapping.value = m
  ccForm.value = { ...m }
}

async function saveCCMapping() {
  try {
    const data = {
      cc_number: ccForm.value.cc_number,
      midi_channel: ccForm.value.midi_channel,
      input_channel: ccForm.value.input_channel,
      label: ccForm.value.label,
      enabled: true,
      device_name: ccForm.value.device_name || null
    }

    if (editingCCMapping.value) {
      await fetchWithAuth(`/api/midi/cc-mappings/${editingCCMapping.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
    } else {
      await fetchWithAuth('/api/midi/cc-mappings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
    }

    await loadCCMappings()
    closeCCModal()
  } catch (e) {
    console.error('Failed to save CC mapping:', e)
    alert('Failed to save CC mapping')
  }
}

async function toggleCCMapping(m) {
  try {
    await fetchWithAuth(`/api/midi/cc-mappings/${m.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !m.enabled })
    })
    await loadCCMappings()
  } catch (e) {
    console.error('Failed to toggle CC mapping:', e)
  }
}

async function deleteCCMapping(m) {
  if (!confirm('Delete this CC mapping?')) return
  try {
    await fetchWithAuth(`/api/midi/cc-mappings/${m.id}`, { method: 'DELETE' })
    await loadCCMappings()
  } catch (e) {
    console.error('Failed to delete CC mapping:', e)
  }
}

// Trigger CRUD
function closeTriggerModal() {
  // Stop listening if active
  if (noteModalListening.value) {
    toggleNoteModalListen()
  }
  showAddTrigger.value = false
  editingTrigger.value = null
  triggerForm.value = { note: 60, midi_channel: -1, action: 'scene', target_id: 1, label: '', device_name: null }
}

function editTrigger(t) {
  editingTrigger.value = t
  triggerForm.value = { ...t }
}

async function saveTrigger() {
  try {
    const data = {
      note: triggerForm.value.note,
      midi_channel: triggerForm.value.midi_channel,
      action: triggerForm.value.action,
      target_id: triggerForm.value.action === 'blackout' ? null : triggerForm.value.target_id,
      label: triggerForm.value.label,
      enabled: true,
      device_name: triggerForm.value.device_name || null
    }

    if (editingTrigger.value) {
      await fetchWithAuth(`/api/midi/triggers/${editingTrigger.value.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
    } else {
      await fetchWithAuth('/api/midi/triggers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      })
    }

    await loadTriggers()
    closeTriggerModal()
  } catch (e) {
    console.error('Failed to save trigger:', e)
    alert('Failed to save trigger')
  }
}

async function toggleTrigger(t) {
  try {
    await fetchWithAuth(`/api/midi/triggers/${t.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !t.enabled })
    })
    await loadTriggers()
  } catch (e) {
    console.error('Failed to toggle trigger:', e)
  }
}

async function deleteTrigger(t) {
  if (!confirm('Delete this trigger?')) return
  try {
    await fetchWithAuth(`/api/midi/triggers/${t.id}`, { method: 'DELETE' })
    await loadTriggers()
  } catch (e) {
    console.error('Failed to delete trigger:', e)
  }
}

</script>

<style scoped>
.midi-control {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header h1 {
  margin: 0;
  font-size: 24px;
}

.card {
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.card h2 {
  margin: 0 0 16px 0;
  font-size: 18px;
  color: var(--text-primary);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.card-header h2 {
  margin: 0;
}

.section-hint {
  margin: 0 0 16px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.status-card .status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 12px;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-item .label {
  color: var(--text-secondary);
}

.status-badge {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
}

.status-badge.success {
  background: rgba(76, 175, 80, 0.2);
  color: #4CAF50;
}

.status-badge.error {
  background: rgba(244, 67, 54, 0.2);
  color: #F44336;
}

.status-badge.inactive {
  background: rgba(158, 158, 158, 0.2);
  color: #9E9E9E;
}

.connection-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.connection-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

.connection-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.feedback-toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--bg-primary);
  border-radius: 6px;
}

.feedback-label {
  font-size: 14px;
  color: var(--text-secondary);
}

.connection-group label {
  font-size: 14px;
  color: var(--text-secondary);
}

.connection-group select {
  padding: 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
}

/* Network MIDI styles */
.network-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.network-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.network-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.server-section h3,
.peers-section h3 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: var(--text-primary);
}

.server-section .hint {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.server-controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-inline {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.form-inline label {
  font-size: 14px;
  color: var(--text-secondary);
}

.form-inline input[type="number"] {
  width: 80px;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-inline input[type="text"] {
  width: 150px;
  padding: 6px 8px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
  background: var(--bg-primary);
  color: var(--text-primary);
}

.server-info {
  margin-top: 8px;
}

.peers-section {
  padding-top: 16px;
  border-top: 1px solid var(--border-color);
}

.peers-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.peer-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-primary);
  border-radius: 4px;
}

.peer-name {
  font-weight: 500;
}

.peer-address {
  font-size: 12px;
  color: var(--text-secondary);
  font-family: monospace;
}

.empty-peers {
  padding: 12px;
  background: var(--bg-primary);
  border-radius: 4px;
}

.empty-peers p {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.empty-state {
  text-align: center;
  padding: 32px;
  color: var(--text-secondary);
}

/* Mappings table */
.mappings-table {
  overflow-x: auto;
}

.mappings-table table {
  width: 100%;
  border-collapse: collapse;
}

.mappings-table th,
.mappings-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border-color);
}

.mappings-table th {
  font-size: 12px;
  text-transform: uppercase;
  color: var(--text-secondary);
  font-weight: 600;
}

.mappings-table tr.disabled {
  opacity: 0.5;
}

.toggle {
  position: relative;
  width: 40px;
  height: 20px;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle .slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  transition: 0.2s;
  border-radius: 20px;
}

.toggle .slider:before {
  position: absolute;
  content: "";
  height: 16px;
  width: 16px;
  left: 2px;
  bottom: 2px;
  background-color: white;
  transition: 0.2s;
  border-radius: 50%;
}

.toggle input:checked + .slider {
  background-color: var(--accent-color);
}

.toggle input:checked + .slider:before {
  transform: translateX(20px);
}

/* Modal styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal {
  background: var(--bg-secondary);
  border-radius: 8px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--border-color);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px;
  border-top: 1px solid var(--border-color);
}

.input-with-listen {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-with-listen input {
  flex: 1;
  width: auto;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-help {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 6px;
  margin-bottom: 0;
}

.btn {
  padding: 8px 16px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
  font-size: 14px;
  transition: background 0.2s;
}

.btn-primary {
  background: var(--accent-color);
  color: white;
}

.btn-primary:hover {
  background: var(--accent-color-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: var(--bg-primary);
  color: var(--text-primary);
  border: 1px solid var(--border-color);
}

.btn-secondary:hover {
  background: var(--bg-secondary);
}

.btn-warning {
  background: #ff9800;
  color: white;
}

.btn-danger {
  background: #f44336;
  color: white;
}

.btn-small {
  padding: 4px 8px;
  font-size: 12px;
}

@media (max-width: 768px) {
  .connection-row {
    grid-template-columns: 1fr;
  }

  .form-row {
    grid-template-columns: 1fr;
  }
}

/* Multi-device styles */
.device-list {
  margin-bottom: 16px;
}

.device-list h3 {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 8px 0;
}

.device-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.device-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-primary);
  border-radius: 6px;
  border: 1px solid var(--border-color);
}

.device-item .device-name {
  font-size: 14px;
  color: var(--text-primary);
}

.device-item .device-name.connected {
  color: var(--success-color, #4ade80);
  font-weight: 500;
}

.device-cell {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-secondary);
}

.device-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-primary);
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-left: 8px;
}
</style>

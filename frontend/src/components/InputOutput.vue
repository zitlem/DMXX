<template>
  <div>
    <div class="card-header" style="margin-bottom: 16px;">
      <h2 class="card-title">Input / Output Configuration</h2>
    </div>

    <!-- Three Column Layout -->
    <div class="io-grid">
      <!-- Inputs Column -->
      <div class="io-column">
        <div class="io-column-header">
          <h3>Inputs</h3>
        </div>
        <div class="io-column-content">
          <div class="protocol-list">
            <div v-for="proto in inputProtocols" :key="proto.id" class="protocol-item">
              <div class="protocol-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/>
                  <path d="M3 3v5h5"/>
                  <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/>
                  <path d="M16 16h5v5"/>
                </svg>
              </div>
              <div class="protocol-info">
                <div class="protocol-name">{{ proto.name }}</div>
                <div class="protocol-desc">{{ proto.description }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Universes Column -->
      <div class="io-column universes-column">
        <div class="io-column-header">
          <h3>Universes</h3>
          <button class="btn btn-small btn-primary" @click="showAddUniverse = true">+ Add</button>
        </div>
        <div class="io-column-content">
          <div v-for="universe in ioConfig.universes" :key="universe.id" class="universe-card">
            <div class="universe-header">
              <div class="universe-info">
                <span class="universe-label">{{ universe.label }}</span>
                <span class="universe-id">ID: {{ universe.id }}</span>
              </div>
              <div class="universe-actions">
                <button class="btn btn-small btn-secondary" @click="editUniverse(universe)">Edit</button>
                <button class="btn btn-small btn-danger" @click="confirmDeleteUniverse(universe)">Delete</button>
              </div>
            </div>

            <!-- Input Section -->
            <div class="io-section-row">
              <div class="dropdown-section">
                <span class="io-section-label">Input</span>
                <select
                  class="form-select io-select"
                  :value="universe.input.input_type"
                  @change="updateInput(universe.id, $event.target.value)"
                >
                  <option v-for="proto in inputProtocols" :key="proto.id" :value="proto.id">
                    {{ proto.name }}
                  </option>
                </select>
                <div v-if="universe.input.input_type !== 'none'" class="io-config">
                  <button
                    class="btn btn-small"
                    :class="universe.input.enabled ? 'btn-success' : 'btn-secondary'"
                    @click="toggleInput(universe.id, !universe.input.enabled)"
                  >
                    {{ universe.input.enabled ? 'On' : 'Off' }}
                  </button>
                  <button class="btn btn-small btn-secondary" @click="configureInput(universe)">
                    Config
                  </button>
                  <span v-if="universe.input.status" :class="['status-indicator', universe.input.status.running ? 'active' : '']"></span>
                </div>
              </div>
            </div>

            <!-- Universe Visual Row -->
            <div class="visual-row">
              <div class="universe-visual">
                <div class="connection-line input-line" :class="{ active: universe.input.enabled && universe.input.input_type !== 'none' }"></div>
                <div class="universe-box">
                  <span>U{{ universe.id }}</span>
                </div>
                <div class="connection-lines-container">
                  <div
                    v-for="(output, idx) in universe.outputs"
                    :key="output.id || idx"
                    class="connection-line output-line"
                    :class="{ active: output.enabled }"
                  ></div>
                </div>
              </div>
            </div>

            <!-- Multiple Outputs Section -->
            <div class="outputs-section">
              <div class="outputs-header">
                <span class="io-section-label">Outputs ({{ universe.outputs.length }})</span>
                <button class="btn btn-small btn-primary" @click="addOutput(universe)">+ Add</button>
              </div>
              <div class="outputs-list">
                <div v-for="(output, idx) in universe.outputs" :key="output.id || idx" class="output-item">
                  <div class="output-info">
                    <select
                      class="form-select io-select output-type-select"
                      :value="output.device_type"
                      @change="updateOutputType(universe.id, output, $event.target.value)"
                    >
                      <option v-for="proto in outputProtocols" :key="proto.id" :value="proto.id">
                        {{ proto.name }}
                      </option>
                    </select>
                    <span v-if="output.status" :class="['status-indicator', output.status.running ? 'active' : '']"></span>
                  </div>
                  <div class="output-controls">
                    <button
                      class="btn btn-small"
                      :class="output.enabled ? 'btn-success' : 'btn-secondary'"
                      @click="toggleOutputItem(universe.id, output)"
                    >
                      {{ output.enabled ? 'On' : 'Off' }}
                    </button>
                    <button class="btn btn-small btn-secondary" @click="configureOutputItem(universe, output)">
                      Config
                    </button>
                    <button
                      v-if="universe.outputs.length > 1 || output.id"
                      class="btn btn-small btn-danger"
                      @click="deleteOutput(universe.id, output)"
                    >
                      X
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Passthrough Section -->
            <div class="passthrough-section" v-if="universe.input.input_type !== 'none'">
              <div class="passthrough-controls">
                <label class="passthrough-label">Passthrough</label>
                <select
                  class="form-select passthrough-mode-select"
                  :value="universe.passthrough.passthrough_mode || 'off'"
                  @change="updatePassthroughMode(universe.id, $event.target.value, universe.passthrough.merge_mode)"
                >
                  <option value="off">Off</option>
                  <option value="view_only">View Only (faders only)</option>
                  <option value="faders_output">Faders + Output</option>
                </select>
                <select
                  v-if="universe.passthrough.passthrough_mode && universe.passthrough.passthrough_mode !== 'off'"
                  class="form-select merge-mode-select"
                  :value="universe.passthrough.merge_mode || 'htp'"
                  @change="updatePassthroughMode(universe.id, universe.passthrough.passthrough_mode, $event.target.value)"
                >
                  <option value="htp">HTP</option>
                  <option value="ltp">LTP</option>
                </select>
              </div>
              <router-link
                v-if="universe.passthrough.passthrough_mode && universe.passthrough.passthrough_mode !== 'off'"
                to="/mapping"
                class="btn btn-small btn-secondary mapping-link"
              >
                Channel Mapping
              </router-link>
              <button class="btn btn-small btn-secondary help-btn" @click="showLoopbackHelp = true" title="Loopback prevention help">
                ?
              </button>
            </div>

            <!-- Input Monitor Section -->
            <div v-if="universe.input.input_type !== 'none' && universe.input.enabled" class="input-monitor-section">
              <div class="input-monitor-header" @click="toggleInputMonitor(universe.id)">
                <div class="input-monitor-title">
                  <svg
                    class="expand-icon"
                    :class="{ expanded: inputMonitorExpanded[universe.id] }"
                    xmlns="http://www.w3.org/2000/svg"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="9 18 15 12 9 6"></polyline>
                  </svg>
                  <span>Input Monitor</span>
                </div>
                <div class="input-monitor-stats">
                  <span class="stat">
                    <span class="stat-value">{{ getActiveInputChannelCount(universe.id) }}</span>
                    <span class="stat-label">active</span>
                  </span>
                  <span v-if="universe.input.status" class="stat">
                    <span class="stat-value">{{ universe.input.status.packets_received || 0 }}</span>
                    <span class="stat-label">packets</span>
                  </span>
                </div>
              </div>

              <div v-if="inputMonitorExpanded[universe.id]" class="input-monitor-content">
                <div class="input-dmx-grid">
                  <div
                    v-for="channel in 512"
                    :key="channel"
                    class="input-dmx-cell"
                    :class="{ active: getInputValue(universe.id, channel) > 0 }"
                    :style="getInputCellStyle(universe.id, channel)"
                  >
                    <span class="cell-channel">{{ channel }}</span>
                    <span class="cell-value">{{ getInputValue(universe.id, channel) }} | {{ Math.round(getInputValue(universe.id, channel) / 255 * 100) }}%</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div v-if="ioConfig.universes.length === 0" class="no-universes">
            No universes configured. Add universes in the Patch page.
          </div>
        </div>
      </div>

      <!-- Outputs Column -->
      <div class="io-column">
        <div class="io-column-header">
          <h3>Outputs</h3>
        </div>
        <div class="io-column-content">
          <div class="protocol-list">
            <div v-for="proto in outputProtocols" :key="proto.id" class="protocol-item">
              <div class="protocol-icon">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"/>
                  <line x1="12" y1="8" x2="12" y2="12"/>
                  <line x1="12" y1="16" x2="12.01" y2="16"/>
                </svg>
              </div>
              <div class="protocol-info">
                <div class="protocol-name">{{ proto.name }}</div>
                <div class="protocol-desc">{{ proto.description }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Input Config Modal -->
    <div v-if="showInputConfig" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Configure Input - {{ showInputConfig.label }}</h3>
          <button class="modal-close" @click="showInputConfig = null">&times;</button>
        </div>

        <div v-if="showInputConfig.input.input_type === 'artnet_input'" class="config-form">
          <div class="form-group">
            <label class="form-label">Listen IP (0.0.0.0 for all)</label>
            <input type="text" class="form-input" v-model="inputConfigForm.bind_ip" placeholder="0.0.0.0">
            <p class="form-help">This must be an IP address on THIS machine (e.g., 0.0.0.0 or your server's IP), not the remote sender's IP. To filter packets by sender, use "Source IP Filter" below.</p>
          </div>
          <div class="form-group">
            <label class="form-label">Port</label>
            <input type="number" class="form-input" v-model.number="inputConfigForm.port" placeholder="6454">
          </div>
          <div class="form-group">
            <label class="form-label">Art-Net Universe (0-based)</label>
            <input type="number" class="form-input" v-model.number="inputConfigForm.artnet_universe" min="0" placeholder="0">
          </div>
          <div class="form-group">
            <label class="form-label">Source IP Filter (only accept from this IP, empty = all)</label>
            <input type="text" class="form-input" v-model="inputConfigForm.source_ip" placeholder="">
          </div>
          <div class="form-group">
            <label class="form-label">Ignore IP (reject packets from this IP)</label>
            <input type="text" class="form-input" v-model="inputConfigForm.ignore_ip" placeholder="">
          </div>
          <div class="form-group">
            <label style="display: flex; align-items: center; gap: 8px;">
              <input type="checkbox" v-model="inputConfigForm.ignore_self">
              Ignore Self (auto-filter packets from this machine)
            </label>
          </div>
        </div>

        <div v-if="showInputConfig.input.input_type === 'sacn_input'" class="config-form">
          <div class="form-group">
            <label class="form-label">sACN Universe</label>
            <input type="number" class="form-input" v-model.number="inputConfigForm.sacn_universe" min="1" placeholder="1">
          </div>
          <div class="form-group">
            <label style="display: flex; align-items: center; gap: 8px;">
              <input type="checkbox" v-model="inputConfigForm.multicast">
              Use Multicast
            </label>
          </div>
          <div class="form-group">
            <label class="form-label">Bind IP (0.0.0.0 for all interfaces)</label>
            <input type="text" class="form-input" v-model="inputConfigForm.bind_ip" placeholder="0.0.0.0">
            <p class="form-help">This must be an IP address on THIS machine (e.g., 0.0.0.0 or your server's IP), not the remote sender's IP. To filter packets by sender, use "Source IP Filter" below.</p>
          </div>
          <div class="form-group">
            <label class="form-label">Source IP Filter (only accept from this IP, empty = all)</label>
            <input type="text" class="form-input" v-model="inputConfigForm.source_ip" placeholder="">
          </div>
          <div class="form-group">
            <label class="form-label">Ignore IP (reject packets from this IP)</label>
            <input type="text" class="form-input" v-model="inputConfigForm.ignore_ip" placeholder="">
          </div>
          <div class="form-group">
            <label style="display: flex; align-items: center; gap: 8px;">
              <input type="checkbox" v-model="inputConfigForm.ignore_self">
              Ignore Self (auto-filter packets from this machine)
            </label>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showInputConfig = null">Cancel</button>
          <button class="btn btn-primary" @click="saveInputConfig">Save</button>
        </div>
      </div>
    </div>

    <!-- Output Config Modal -->
    <div v-if="showOutputConfig" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Configure Output - {{ showOutputConfig.universe.label }}</h3>
          <button class="modal-close" @click="showOutputConfig = null">&times;</button>
        </div>

        <div v-if="showOutputConfig.output.device_type === 'artnet'" class="config-form">
          <div class="form-group">
            <label class="form-label">Target IP (255.255.255.255 for broadcast)</label>
            <input type="text" class="form-input" v-model="outputConfigForm.ip" placeholder="255.255.255.255">
          </div>
          <div class="form-group">
            <label class="form-label">Port</label>
            <input type="number" class="form-input" v-model.number="outputConfigForm.port" placeholder="6454">
          </div>
          <div class="form-group">
            <label class="form-label">Art-Net Universe (0-based)</label>
            <input type="number" class="form-input" v-model.number="outputConfigForm.universe" min="0" placeholder="0">
          </div>
        </div>

        <div v-if="showOutputConfig.output.device_type === 'sacn'" class="config-form">
          <div class="form-group">
            <label class="form-label">sACN Universe</label>
            <input type="number" class="form-input" v-model.number="outputConfigForm.universe" min="1" placeholder="1">
          </div>
          <div class="form-group">
            <label style="display: flex; align-items: center; gap: 8px;">
              <input type="checkbox" v-model="outputConfigForm.multicast">
              Use Multicast
            </label>
          </div>
          <div v-if="!outputConfigForm.multicast" class="form-group">
            <label class="form-label">Unicast IP</label>
            <input type="text" class="form-input" v-model="outputConfigForm.ip" placeholder="10.0.0.1">
          </div>
        </div>

        <div v-if="showOutputConfig.output.device_type === 'mock' || showOutputConfig.output.device_type === 'dummy'" class="config-form">
          <p style="color: var(--text-secondary);">No configuration needed for dummy output.</p>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showOutputConfig = null">Cancel</button>
          <button class="btn btn-primary" @click="saveOutputConfig">Save</button>
        </div>
      </div>
    </div>

    <!-- Add/Edit Universe Modal -->
    <div v-if="showAddUniverse || editingUniverse" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingUniverse ? 'Edit Universe' : 'Add Universe' }}</h3>
          <button class="modal-close" @click="closeUniverseModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Label</label>
          <input type="text" class="form-input" v-model="universeForm.label" placeholder="e.g., Universe 1">
        </div>

        <div class="form-group">
          <label class="form-label">Output Device Type</label>
          <select class="form-select" v-model="universeForm.device_type">
            <option v-for="proto in outputProtocols" :key="proto.id" :value="proto.id">
              {{ proto.name }}
            </option>
          </select>
        </div>

        <div v-if="universeForm.device_type === 'artnet'" class="form-group">
          <label class="form-label">Art-Net IP (broadcast)</label>
          <input type="text" class="form-input" v-model="universeForm.config.ip" placeholder="255.255.255.255">
        </div>

        <div class="form-group">
          <label style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" v-model="universeForm.enabled">
            Enabled
          </label>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeUniverseModal">Cancel</button>
          <button class="btn btn-primary" @click="saveUniverse" :disabled="!universeForm.label">
            {{ editingUniverse ? 'Update' : 'Add' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Universe Confirmation -->
    <div v-if="deletingUniverse" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Delete Universe</h3>
          <button class="modal-close" @click="deletingUniverse = null">&times;</button>
        </div>
        <p>Are you sure you want to delete this universe?</p>
        <p style="color: var(--text-secondary);">{{ deletingUniverse.label }} (ID: {{ deletingUniverse.id }})</p>
        <p style="color: var(--error); font-size: 12px;">Warning: This will also delete any patches assigned to this universe.</p>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="deletingUniverse = null">Cancel</button>
          <button class="btn btn-danger" @click="deleteUniverse">Delete</button>
        </div>
      </div>
    </div>

    <!-- Loopback Prevention Help Modal -->
    <div v-if="showLoopbackHelp" class="modal-overlay">
      <div class="modal" style="max-width: 600px;">
        <div class="modal-header">
          <h3 class="modal-title">{{ loopbackHelp?.title || 'Loopback Prevention' }}</h3>
          <button class="modal-close" @click="showLoopbackHelp = false">&times;</button>
        </div>
        <div class="help-content">
          <p style="color: var(--text-secondary); margin-bottom: 16px;">{{ loopbackHelp?.description }}</p>
          <div v-for="option in loopbackHelp?.options" :key="option.method" class="help-option">
            <div class="help-option-header">
              <span class="help-option-method">{{ option.method }}</span>
            </div>
            <p class="help-option-desc">{{ option.description }}</p>
            <div class="help-pros-cons">
              <div class="help-pros">
                <span class="label">Pros:</span>
                <span v-for="pro in option.pros" :key="pro" class="pro-item">{{ pro }}</span>
              </div>
              <div class="help-cons">
                <span class="label">Cons:</span>
                <span v-for="con in option.cons" :key="con" class="con-item">{{ con }}</span>
              </div>
            </div>
          </div>
          <div v-if="loopbackHelp?.recommendation" class="help-recommendation">
            <strong>Recommendation:</strong> {{ loopbackHelp.recommendation }}
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="showLoopbackHelp = false">Got it</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useThemeStore } from '../stores/theme.js'
import { wsManager } from '../websocket.js'

const authStore = useAuthStore()
const themeStore = useThemeStore()

const ioConfig = ref({ universes: [] })
const inputProtocols = ref([])
const outputProtocols = ref([])
const showInputConfig = ref(null)
const showOutputConfig = ref(null)
const inputConfigForm = ref({})
const outputConfigForm = ref({})

// Input monitor state
const inputMonitorExpanded = reactive({})
const inputValues = reactive({})

// Help modal state
const showLoopbackHelp = ref(false)
const loopbackHelp = ref(null)

// Universe management
const showAddUniverse = ref(false)
const editingUniverse = ref(null)
const deletingUniverse = ref(null)
const universeForm = ref({
  label: '',
  device_type: 'artnet',
  config: { ip: '255.255.255.255' },
  enabled: false
})

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

async function loadIOConfig() {
  try {
    const response = await fetchWithAuth(`/api/io?_t=${Date.now()}`)
    const data = await response.json()
    ioConfig.value = data
    inputProtocols.value = data.input_protocols || []
    outputProtocols.value = data.output_protocols || []
  } catch (e) {
    console.error('Failed to load I/O config:', e)
  }
}

async function updateInput(universeId, inputType) {
  try {
    await fetchWithAuth(`/api/io/${universeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input_type: inputType,
        input_enabled: inputType !== 'none'
      })
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to update input:', e)
  }
}

async function updateOutput(universeId, deviceType) {
  try {
    await fetchWithAuth(`/api/io/${universeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_type: deviceType
      })
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to update output:', e)
  }
}

async function toggleInput(universeId, enabled) {
  try {
    const endpoint = enabled ? 'enable' : 'disable'
    await fetchWithAuth(`/api/io/${universeId}/input/${endpoint}`, {
      method: 'POST'
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to toggle input:', e)
  }
}

async function toggleOutput(universeId, enabled) {
  try {
    await fetchWithAuth(`/api/io/${universeId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled })
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to toggle output:', e)
  }
}

async function updatePassthroughMode(universeId, passthroughMode, mergeMode = 'htp') {
  try {
    await fetchWithAuth(`/api/io/${universeId}/passthrough`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        passthrough_mode: passthroughMode,
        merge_mode: mergeMode
      })
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to update passthrough:', e)
  }
}

// Legacy function for backwards compatibility
async function updatePassthrough(universeId, enabled, mode, showUi = false) {
  // Convert old format to new
  let passthroughMode = 'off'
  if (enabled && showUi) passthroughMode = 'faders_output'
  else if (enabled && !showUi) passthroughMode = 'output_only'
  else if (!enabled && showUi) passthroughMode = 'view_only'

  await updatePassthroughMode(universeId, passthroughMode, mode)
}

async function loadLoopbackHelp() {
  try {
    const response = await fetchWithAuth('/api/io/help/loopback')
    loopbackHelp.value = await response.json()
  } catch (e) {
    console.error('Failed to load loopback help:', e)
  }
}

function configureInput(universe) {
  showInputConfig.value = universe
  inputConfigForm.value = {
    bind_ip: '0.0.0.0',  // Default to all interfaces
    ...universe.input.config
  }
}

function configureOutput(universe) {
  // Legacy - configures first output
  const output = universe.outputs[0] || universe.output
  showOutputConfig.value = { universe, output }
  outputConfigForm.value = { ...output.config }
}

function configureOutputItem(universe, output) {
  showOutputConfig.value = { universe, output }
  outputConfigForm.value = { ...output.config }
}

async function saveInputConfig() {
  try {
    await fetchWithAuth(`/api/io/${showInputConfig.value.id}/input`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input_type: showInputConfig.value.input.input_type,
        input_config: inputConfigForm.value,
        input_enabled: showInputConfig.value.input.enabled
      })
    })
    showInputConfig.value = null
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to save input config:', e)
  }
}

async function saveOutputConfig() {
  try {
    const { universe, output } = showOutputConfig.value
    if (output.id) {
      // Update existing output via new multi-output endpoint
      await fetchWithAuth(`/api/io/${universe.id}/outputs/${output.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_type: output.device_type,
          config_json: outputConfigForm.value,
          enabled: output.enabled
        })
      })
    } else {
      // Legacy single output - update via old endpoint
      await fetchWithAuth(`/api/io/${universe.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          config_json: outputConfigForm.value
        })
      })
    }
    showOutputConfig.value = null
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to save output config:', e)
  }
}

// Multiple outputs functions
async function addOutput(universe) {
  try {
    await fetchWithAuth(`/api/io/${universe.id}/outputs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        device_type: 'artnet',
        config_json: { ip: '255.255.255.255' },
        enabled: true
      })
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to add output:', e)
  }
}

async function updateOutputType(universeId, output, deviceType) {
  try {
    if (output.id) {
      await fetchWithAuth(`/api/io/${universeId}/outputs/${output.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_type: deviceType,
          config_json: output.config || {},
          enabled: output.enabled
        })
      })
    } else {
      // Legacy - use old endpoint
      await fetchWithAuth(`/api/io/${universeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_type: deviceType
        })
      })
    }
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to update output type:', e)
  }
}

async function toggleOutputItem(universeId, output) {
  try {
    const newEnabled = !output.enabled
    if (output.id) {
      await fetchWithAuth(`/api/io/${universeId}/outputs/${output.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          device_type: output.device_type,
          config_json: output.config || {},
          enabled: newEnabled
        })
      })
    } else {
      // Legacy
      await fetchWithAuth(`/api/io/${universeId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newEnabled })
      })
    }
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to toggle output:', e)
  }
}

async function deleteOutput(universeId, output) {
  if (!output.id) {
    // Can't delete legacy output
    return
  }
  try {
    await fetchWithAuth(`/api/io/${universeId}/outputs/${output.id}`, {
      method: 'DELETE'
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to delete output:', e)
  }
}

// Universe management functions
function editUniverse(universe) {
  editingUniverse.value = universe
  universeForm.value = {
    label: universe.label,
    device_type: universe.output.device_type,
    config: { ...universe.output.config },
    enabled: universe.output.enabled
  }
}

function closeUniverseModal() {
  showAddUniverse.value = false
  editingUniverse.value = null
  universeForm.value = { label: '', device_type: 'artnet', config: { ip: '255.255.255.255' }, enabled: false }
}

async function saveUniverse() {
  try {
    const url = editingUniverse.value
      ? `/api/universes/${editingUniverse.value.id}`
      : '/api/universes'
    const method = editingUniverse.value ? 'PUT' : 'POST'

    const response = await fetchWithAuth(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        label: universeForm.value.label,
        device_type: universeForm.value.device_type,
        config_json: universeForm.value.config,
        enabled: universeForm.value.enabled
      })
    })

    if (response.ok) {
      closeUniverseModal()
      await loadIOConfig()
    }
  } catch (e) {
    console.error('Failed to save universe:', e)
  }
}

function confirmDeleteUniverse(universe) {
  deletingUniverse.value = universe
}

async function deleteUniverse() {
  try {
    await fetchWithAuth(`/api/universes/${deletingUniverse.value.id}`, {
      method: 'DELETE'
    })
    deletingUniverse.value = null
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to delete universe:', e)
  }
}

// Input monitor functions
const inputPollIntervals = {}

function handleInputValues(data) {
  inputValues[data.universe_id] = [...data.values]
}

function toggleInputMonitor(universeId) {
  inputMonitorExpanded[universeId] = !inputMonitorExpanded[universeId]
  if (inputMonitorExpanded[universeId]) {
    wsManager.requestInputValues(universeId)
    // Poll every 200ms while expanded for responsive updates
    inputPollIntervals[universeId] = setInterval(() => {
      wsManager.requestInputValues(universeId)
    }, 200)
  } else {
    // Stop polling when collapsed
    if (inputPollIntervals[universeId]) {
      clearInterval(inputPollIntervals[universeId])
      delete inputPollIntervals[universeId]
    }
  }
}

function getInputValue(universeId, channel) {
  const values = inputValues[universeId]
  if (!values) return 0
  return values[channel - 1] || 0
}

function getActiveInputChannelCount(universeId) {
  const values = inputValues[universeId]
  if (!values) return 0
  return values.filter(v => v > 0).length
}

function getInputCellStyle(universeId, channel) {
  const value = getInputValue(universeId, channel)
  if (value > 0) {
    const intensity = value / 255
    return {
      background: `rgba(74, 222, 128, ${0.3 + intensity * 0.7})`
    }
  }
  return {}
}

onMounted(() => {
  loadIOConfig()
  loadLoopbackHelp()

  // Subscribe to input value updates
  wsManager.on('input_values', handleInputValues)

  // Request current input values
  wsManager.requestAllInputValues()
})

onUnmounted(() => {
  wsManager.off('input_values', handleInputValues)
  // Clean up all polling intervals
  Object.values(inputPollIntervals).forEach(clearInterval)
})
</script>

<style scoped>
.warning-banner {
  background: var(--warning);
  color: #000;
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.warning-banner a {
  color: #000;
  font-weight: 600;
  text-decoration: underline;
}

.io-grid {
  display: grid;
  grid-template-columns: 200px 1fr 200px;
  gap: 16px;
  min-height: 500px;
}

.io-column {
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border);
  display: flex;
  flex-direction: column;
}

.io-column-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-tertiary);
  border-radius: 8px 8px 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.io-column-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.io-column-content {
  padding: 12px;
  flex: 1;
  overflow-y: auto;
}

.universes-column {
  min-width: 400px;
}

.protocol-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.protocol-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border);
}

.protocol-icon {
  color: var(--accent);
  flex-shrink: 0;
}

.protocol-info {
  flex: 1;
  min-width: 0;
}

.protocol-name {
  font-weight: 500;
  font-size: 13px;
}

.protocol-desc {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.universe-card {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
}

.universe-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.universe-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.universe-actions {
  display: flex;
  gap: 6px;
}

.dropdowns-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.dropdown-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.visual-row {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.controls-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.input-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.output-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: flex-end;
}

.universe-label {
  font-weight: 600;
  font-size: 16px;
}

.universe-id {
  font-size: 12px;
  color: var(--text-secondary);
}

.universe-io-row {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.io-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.io-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.io-section-label {
  font-size: 11px;
  text-transform: uppercase;
  color: var(--text-secondary);
  font-weight: 600;
}

.io-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.io-select {
  font-size: 13px;
  padding: 6px 10px;
  min-width: 140px;
}

.io-config {
  display: flex;
  gap: 6px;
}

.io-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-secondary);
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-secondary);
}

.status-indicator.active {
  background: var(--success);
  box-shadow: 0 0 6px var(--success);
}

.universe-visual {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 8px 0;
}

.connection-line {
  width: 40px;
  height: 2px;
  background: var(--border);
  transition: background 0.2s;
}

.connection-line.active {
  background: var(--accent);
  box-shadow: 0 0 4px var(--accent);
}

.connection-lines-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.universe-box {
  width: 50px;
  height: 50px;
  border: 2px solid var(--accent);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
  background: var(--bg-secondary);
}

/* Multiple Outputs Section Styles */
.io-section-row {
  margin-bottom: 12px;
}

.io-section-row .dropdown-section {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.outputs-section {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.outputs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.outputs-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.output-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  gap: 12px;
}

.output-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.output-type-select {
  min-width: 120px;
}

.output-controls {
  display: flex;
  gap: 6px;
  align-items: center;
}

.passthrough-section {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.passthrough-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.passthrough-label {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.passthrough-mode-select {
  font-size: 12px;
  padding: 4px 8px;
  min-width: 160px;
}

.merge-mode-select {
  font-size: 12px;
  padding: 4px 8px;
  min-width: 70px;
}

.passthrough-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
}

.passthrough-toggle input {
  cursor: pointer;
}

.passthrough-mode {
  font-size: 12px;
  padding: 4px 8px;
  flex: 1;
  max-width: 250px;
}

.no-universes {
  text-align: center;
  color: var(--text-secondary);
  padding: 40px 20px;
}

.config-form {
  margin: 16px 0;
}

.btn-success {
  background: var(--success);
  color: #000;
}

/* Input Monitor Styles */
.input-monitor-section {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}

.input-monitor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 8px 0;
}

.input-monitor-header:hover {
  opacity: 0.8;
}

.input-monitor-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
  font-size: 13px;
}

.expand-icon {
  transition: transform 0.2s;
}

.expand-icon.expanded {
  transform: rotate(90deg);
}

.input-monitor-stats {
  display: flex;
  gap: 16px;
}

.stat {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.stat-value {
  font-weight: 600;
  font-size: 14px;
  color: var(--success);
}

.stat-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.input-monitor-content {
  margin-top: 12px;
  padding: 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  border: 1px solid var(--border);
}

.input-dmx-grid {
  display: grid;
  grid-template-columns: repeat(32, 1fr);
  gap: 2px;
}

.input-dmx-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 4px 2px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  color: var(--text-secondary);
  min-width: 0;
}

.input-dmx-cell.active {
  color: white;
}

.cell-channel {
  font-size: 9px;
  opacity: 0.6;
  line-height: 1;
}

.cell-value {
  font-size: 8px;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
}

@media (max-width: 1200px) {
  .input-dmx-grid {
    grid-template-columns: repeat(16, 1fr);
  }
}

@media (max-width: 900px) {
  .input-dmx-grid {
    grid-template-columns: repeat(8, 1fr);
  }
  .cell-value {
    font-size: 9px;
  }
}

/* Show UI toggle and help button styles */
.show-ui-toggle {
  margin-left: auto;
}

.mapping-link {
  text-decoration: none;
  margin-left: 8px;
}

.help-btn {
  width: 24px;
  height: 24px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Help modal styles */
.help-content {
  padding: 16px 0;
  max-height: 60vh;
  overflow-y: auto;
}

.help-option {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}

.help-option-header {
  margin-bottom: 8px;
}

.help-option-method {
  font-weight: 600;
  color: var(--accent);
  font-size: 14px;
}

.help-option-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.help-pros-cons {
  display: flex;
  gap: 16px;
  font-size: 12px;
}

.help-pros, .help-cons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
}

.help-pros .label, .help-cons .label {
  font-weight: 600;
  margin-right: 4px;
}

.pro-item {
  color: var(--success);
  background: rgba(74, 222, 128, 0.1);
  padding: 2px 6px;
  border-radius: 3px;
}

.con-item {
  color: var(--error);
  background: rgba(248, 113, 113, 0.1);
  padding: 2px 6px;
  border-radius: 3px;
}

.help-recommendation {
  margin-top: 16px;
  padding: 12px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid var(--accent);
  border-radius: 6px;
  font-size: 13px;
}

.form-help {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
  margin-bottom: 0;
  line-height: 1.4;
}
</style>

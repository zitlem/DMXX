<template>
  <div>
    <div class="card-header" style="margin-bottom: 16px;">
      <h2 class="card-title">Channel Mapping <button class="btn btn-small btn-secondary help-btn" @click="showHelp = true" title="How channel mapping works">?</button></h2>
      <div class="header-actions">
        <span v-if="mappingStatus.enabled" class="status-badge active">
          Mapping Active ({{ mappingStatus.unmapped_behavior === 'passthrough' ? 'Passthrough' : 'Ignore' }})
        </span>
        <span v-else class="status-badge">Mapping Disabled</span>
        <button class="btn btn-small btn-secondary" @click="syncMapping" title="Force sync runtime from database">Sync</button>
      </div>
    </div>

    <!-- Mapping Configs List -->
    <div class="mapping-configs">
      <div class="configs-header">
        <h3>Saved Mappings</h3>
        <button class="btn btn-primary btn-small" @click="createNewMapping">+ New Mapping</button>
      </div>
      <div class="configs-list">
        <div
          v-for="mapping in mappings"
          :key="mapping.id"
          class="config-card"
          :class="{ active: mapping.enabled }"
        >
          <div class="config-info">
            <span class="config-name">{{ mapping.name }}</span>
            <span class="config-count">{{ mapping.mappings.length }} mappings</span>
          </div>
          <div class="config-actions">
            <button
              class="btn btn-small"
              :class="mapping.enabled ? 'btn-success' : 'btn-secondary'"
              @click="toggleMapping(mapping)"
            >
              {{ mapping.enabled ? 'Active' : 'Enable' }}
            </button>
            <button class="btn btn-small btn-secondary" @click="editMapping(mapping)">Edit</button>
            <button class="btn btn-small btn-danger" @click="confirmDelete(mapping)">Delete</button>
          </div>
        </div>
        <div v-if="mappings.length === 0" class="no-configs">
          No mapping configurations yet. Create one to get started.
        </div>
      </div>
    </div>

    <!-- Edit/Create Modal -->
    <div v-if="showEditor" class="modal-overlay" @click.self="closeEditor">
      <div class="modal modal-large" :class="{ 'modal-visual': editMode === 'visual' }">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingMapping ? 'Edit Mapping' : 'Create Mapping' }}</h3>
          <button class="modal-close" @click="closeEditor">&times;</button>
        </div>

        <div class="editor-content">
          <!-- Name and Settings -->
          <div class="editor-top">
            <div class="form-group">
              <label class="form-label">Mapping Name</label>
              <input type="text" class="form-input" v-model="editorForm.name" placeholder="e.g., Console to Faders">
            </div>
            <div class="form-group">
              <label class="form-label">Unmapped Channel Behavior <small style="color: var(--text-secondary);">(current: {{ editorForm.unmapped_behavior }})</small></label>
              <div class="radio-group">
                <label class="radio-option" :class="{ selected: editorForm.unmapped_behavior === 'passthrough' }">
                  <input type="radio" v-model="editorForm.unmapped_behavior" value="passthrough">
                  <span>Pass through 1:1</span>
                </label>
                <label class="radio-option" :class="{ selected: editorForm.unmapped_behavior === 'ignore' }">
                  <input type="radio" v-model="editorForm.unmapped_behavior" value="ignore">
                  <span>Ignore (zero output)</span>
                </label>
              </div>
            </div>
          </div>

          <!-- Edit Mode Tabs -->
          <div class="edit-mode-tabs">
            <button
              class="tab-btn"
              :class="{ active: editMode === 'table' }"
              @click="editMode = 'table'"
            >
              Table Editor
            </button>
            <button
              class="tab-btn"
              :class="{ active: editMode === 'bulk' }"
              @click="editMode = 'bulk'"
            >
              Bulk Range
            </button>
            <button
              class="tab-btn"
              :class="{ active: editMode === 'visual' }"
              @click="editMode = 'visual'"
            >
              Visual
            </button>
          </div>

          <!-- Table Editor -->
          <div v-if="editMode === 'table'" class="table-editor">
            <div class="table-container">
              <table class="mapping-table">
                <thead>
                  <tr>
                    <th>Source Universe</th>
                    <th>Source Channel</th>
                    <th>Dest Universe</th>
                    <th>Dest Channel</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(m, idx) in editorForm.mappings" :key="idx">
                    <td>
                      <select class="form-select" v-model.number="m.src_universe">
                        <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                      </select>
                    </td>
                    <td>
                      <input type="number" class="form-input" v-model.number="m.src_channel" min="1" max="512">
                    </td>
                    <td>
                      <select class="form-select" v-model.number="m.dst_universe">
                        <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                      </select>
                    </td>
                    <td>
                      <input type="number" class="form-input" v-model.number="m.dst_channel" min="1" max="512">
                    </td>
                    <td>
                      <button class="btn btn-small btn-danger" @click="removeMapping(idx)">X</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <button class="btn btn-secondary" @click="addMapping">+ Add Mapping</button>
          </div>

          <!-- Bulk Range Editor -->
          <div v-if="editMode === 'bulk'" class="bulk-editor">
            <div class="bulk-form">
              <div class="bulk-row">
                <div class="form-group">
                  <label class="form-label">Source Universe</label>
                  <select class="form-select" v-model.number="bulkForm.src_universe">
                    <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">Start Channel</label>
                  <input type="number" class="form-input" v-model.number="bulkForm.src_start" min="1" max="512">
                </div>
                <div class="form-group">
                  <label class="form-label">End Channel</label>
                  <input type="number" class="form-input" v-model.number="bulkForm.src_end" min="1" max="512">
                </div>
              </div>
              <div class="bulk-row">
                <div class="form-group">
                  <label class="form-label">Destination Universe</label>
                  <select class="form-select" v-model.number="bulkForm.dst_universe">
                    <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label">Start Channel</label>
                  <input type="number" class="form-input" v-model.number="bulkForm.dst_start" min="1" max="512">
                </div>
                <div class="form-group bulk-preview">
                  <label class="form-label">Preview</label>
                  <span class="preview-text">
                    {{ bulkForm.src_start }}-{{ bulkForm.src_end }} -> {{ bulkForm.dst_start }}-{{ bulkDstEnd }}
                  </span>
                </div>
              </div>
              <button class="btn btn-primary" @click="applyBulkMapping">Add Range to Mappings</button>
            </div>
          </div>

          <!-- Visual Drag-and-Drop Editor -->
          <div v-if="editMode === 'visual'" class="visual-editor">
            <div class="visual-controls">
              <div class="visual-control-group">
                <label>Source Universe</label>
                <select class="form-select" v-model.number="visualSourceUniverse">
                  <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                </select>
              </div>
              <div class="visual-control-group">
                <label>Destination Universe</label>
                <select class="form-select" v-model.number="visualDestUniverse">
                  <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                </select>
              </div>
              <div class="visual-control-group">
                <label>Channels per row</label>
                <input
                  type="number"
                  class="form-input"
                  v-model.number="visualChannelsPerRow"
                  min="8"
                  max="64"
                  step="1"
                >
              </div>
            </div>

            <div class="visual-grids">
              <div class="visual-grid-section">
                <h4>Source Channels (drag from)</h4>
                <div class="channel-grid" :style="{ gridTemplateColumns: `repeat(${visualChannelsPerRow}, 1fr)` }">
                  <div
                    v-for="ch in 512"
                    :key="'src-' + ch"
                    class="channel-cell source"
                    :class="{
                      mapped: isSourceMapped(visualSourceUniverse, ch),
                      dragging: dragSource?.channel === ch
                    }"
                    draggable="true"
                    @dragstart="startDrag(ch)"
                    @dragend="endDrag"
                  >
                    {{ ch }}
                  </div>
                </div>
              </div>

              <div class="visual-grid-section">
                <h4>Destination Channels (drop onto)</h4>
                <div class="channel-grid" :style="{ gridTemplateColumns: `repeat(${visualChannelsPerRow}, 1fr)` }">
                  <div
                    v-for="ch in 512"
                    :key="'dst-' + ch"
                    class="channel-cell destination"
                    :class="{
                      mapped: isDestMapped(visualDestUniverse, ch),
                      dragover: dragOverDest === ch
                    }"
                    @dragover.prevent="dragOverDest = ch"
                    @dragleave="dragOverDest = null"
                    @drop="dropOnDest(ch)"
                  >
                    {{ ch }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Current Mappings Summary -->
          <div class="mappings-summary">
            <h4>Current Mappings ({{ editorForm.mappings.length }})</h4>
            <div class="summary-list" v-if="editorForm.mappings.length > 0">
              <span
                v-for="(m, idx) in editorForm.mappings.slice(0, 20)"
                :key="idx"
                class="mapping-chip"
              >
                U{{ m.src_universe }}.{{ m.src_channel }} -> U{{ m.dst_universe }}.{{ m.dst_channel }}
                <button class="chip-remove" @click="removeMapping(idx)">&times;</button>
              </span>
              <span v-if="editorForm.mappings.length > 20" class="more-count">
                +{{ editorForm.mappings.length - 20 }} more
              </span>
            </div>
            <div v-else class="no-mappings">No mappings defined yet.</div>
            <button v-if="editorForm.mappings.length > 0" class="btn btn-small btn-danger" @click="clearAllMappings">Clear All</button>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeEditor">Cancel</button>
          <button class="btn btn-primary" @click="saveMapping" :disabled="!editorForm.name">Save</button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div v-if="deletingMapping" class="modal-overlay" @click.self="deletingMapping = null">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Delete Mapping</h3>
          <button class="modal-close" @click="deletingMapping = null">&times;</button>
        </div>
        <p>Are you sure you want to delete "{{ deletingMapping.name }}"?</p>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="deletingMapping = null">Cancel</button>
          <button class="btn btn-danger" @click="deleteMapping">Delete</button>
        </div>
      </div>
    </div>

    <!-- Help Modal -->
    <div v-if="showHelp" class="modal-overlay" @click.self="showHelp = false">
      <div class="modal" style="max-width: 650px;">
        <div class="modal-header">
          <h3 class="modal-title">How Channel Mapping Works</h3>
          <button class="modal-close" @click="showHelp = false">&times;</button>
        </div>
        <div class="help-content">
          <p class="help-intro">Channel mapping routes input channels to different output channels. This is useful for remapping console faders, combining inputs, or reorganizing your DMX layout.</p>

          <div class="help-section">
            <h4>Mapped Channels</h4>
            <p>Input channels with mappings <strong>only</strong> go to their mapped destination(s). They do NOT also pass through 1:1.</p>
            <p class="help-example">Example: Ch1 → Ch12 means input Ch1 controls output Ch12. Output Ch1 is not affected by input Ch1.</p>
          </div>

          <div class="help-section">
            <h4>One-to-Many Mapping</h4>
            <p>A single input channel can map to multiple output channels.</p>
            <p class="help-example">Example: Ch1 → Ch10, Ch11, Ch12 means input Ch1 controls all three output channels simultaneously.</p>
          </div>

          <div class="help-section">
            <h4>Unmapped Channel Behavior</h4>
            <div class="help-option">
              <span class="help-option-label">Pass through 1:1</span>
              <p>Channels without mappings pass through normally (input Ch5 → output Ch5). Mapped destinations are protected from being overwritten.</p>
            </div>
            <div class="help-option">
              <span class="help-option-label">Ignore (zero output)</span>
              <p>Only mapped channels produce output. All unmapped input channels are ignored.</p>
            </div>
          </div>

          <div class="help-section">
            <h4>Merge Modes (HTP/LTP)</h4>
            <p>The merge mode (configured in Input/Output) applies to the <strong>destination</strong> channels after mapping.</p>
            <ul>
              <li><strong>HTP (Highest Takes Precedence)</strong>: Highest value between local faders and mapped input wins</li>
              <li><strong>LTP (Latest Takes Precedence)</strong>: Most recent change wins (mapped input overrides local faders)</li>
            </ul>
          </div>

          <div class="help-section">
            <h4>Cross-Universe Mapping</h4>
            <p>You can map input from one universe to output channels in a different universe.</p>
            <p class="help-example">Example: Universe 1 Ch1 → Universe 2 Ch1 routes input from universe 1 to output on universe 2.</p>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-primary" @click="showHelp = false">Got it</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useDmxStore } from '../stores/dmx.js'

const authStore = useAuthStore()
const dmxStore = useDmxStore()

const mappings = ref([])
const mappingStatus = ref({ enabled: false, mapping_count: 0 })
const universes = ref([])

// Help modal
const showHelp = ref(false)

// Editor state
const showEditor = ref(false)
const editingMapping = ref(null)
const editMode = ref('table')
const editorForm = ref({
  name: '',
  unmapped_behavior: 'passthrough',
  mappings: []
})

// Bulk form
const bulkForm = ref({
  src_universe: 1,
  src_start: 1,
  src_end: 16,
  dst_universe: 1,
  dst_start: 1
})

// Visual editor state
const visualSourceUniverse = ref(1)
const visualDestUniverse = ref(1)
const visualChannelsPerRow = ref(32)
const dragSource = ref(null)
const dragOverDest = ref(null)

// Delete confirmation
const deletingMapping = ref(null)

// Computed
const bulkDstEnd = computed(() => {
  const range = bulkForm.value.src_end - bulkForm.value.src_start
  return bulkForm.value.dst_start + range
})

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

async function loadMappings() {
  try {
    const response = await fetchWithAuth('/api/mapping')
    const data = await response.json()
    mappings.value = data.mappings || []
    mappingStatus.value = data.status || { enabled: false }
  } catch (e) {
    console.error('Failed to load mappings:', e)
  }
}

async function loadUniverses() {
  await dmxStore.loadUniverses()
  universes.value = dmxStore.universes
  if (universes.value.length > 0) {
    visualSourceUniverse.value = universes.value[0].id
    visualDestUniverse.value = universes.value[0].id
    bulkForm.value.src_universe = universes.value[0].id
    bulkForm.value.dst_universe = universes.value[0].id
  }
}

function createNewMapping() {
  editingMapping.value = null
  editorForm.value = {
    name: '',
    unmapped_behavior: 'passthrough',
    mappings: []
  }
  editMode.value = 'table'
  showEditor.value = true
}

function editMapping(mapping) {
  console.log('editMapping called with:', JSON.stringify(mapping, null, 2))
  editingMapping.value = mapping
  editorForm.value = {
    name: mapping.name,
    unmapped_behavior: mapping.unmapped_behavior,
    mappings: [...mapping.mappings]
  }
  console.log('editorForm.unmapped_behavior set to:', editorForm.value.unmapped_behavior)
  editMode.value = 'table'
  showEditor.value = true
}

function closeEditor() {
  showEditor.value = false
  editingMapping.value = null
}

async function saveMapping() {
  if (!editorForm.value.name) return

  try {
    const payload = {
      name: editorForm.value.name,
      enabled: editingMapping.value?.enabled || false,
      unmapped_behavior: editorForm.value.unmapped_behavior,
      mappings: editorForm.value.mappings
    }

    console.log('Saving mapping with payload:', JSON.stringify(payload, null, 2))

    const url = editingMapping.value
      ? `/api/mapping/${editingMapping.value.id}`
      : '/api/mapping'
    const method = editingMapping.value ? 'PUT' : 'POST'

    const response = await fetchWithAuth(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (response.ok) {
      closeEditor()
      await loadMappings()
    }
  } catch (e) {
    console.error('Failed to save mapping:', e)
  }
}

async function toggleMapping(mapping) {
  try {
    if (mapping.enabled) {
      // Disable all mappings
      await fetchWithAuth('/api/mapping/disable', { method: 'POST' })
    } else {
      // Enable this mapping
      await fetchWithAuth(`/api/mapping/${mapping.id}/enable`, { method: 'POST' })
    }
    await loadMappings()
  } catch (e) {
    console.error('Failed to toggle mapping:', e)
  }
}

async function syncMapping() {
  try {
    const response = await fetchWithAuth('/api/mapping/sync', { method: 'POST' })
    const data = await response.json()
    console.log('Sync result:', data)
    await loadMappings()
  } catch (e) {
    console.error('Failed to sync mapping:', e)
  }
}

function confirmDelete(mapping) {
  deletingMapping.value = mapping
}

async function deleteMapping() {
  if (!deletingMapping.value) return

  try {
    await fetchWithAuth(`/api/mapping/${deletingMapping.value.id}`, { method: 'DELETE' })
    deletingMapping.value = null
    await loadMappings()
  } catch (e) {
    console.error('Failed to delete mapping:', e)
  }
}

// Table editor functions
function addMapping() {
  const defaultUniverse = universes.value[0]?.id || 1
  editorForm.value.mappings.push({
    src_universe: defaultUniverse,
    src_channel: 1,
    dst_universe: defaultUniverse,
    dst_channel: 1
  })
}

function removeMapping(idx) {
  editorForm.value.mappings.splice(idx, 1)
}

function clearAllMappings() {
  editorForm.value.mappings = []
}

// Bulk editor functions
function applyBulkMapping() {
  const rangeSize = bulkForm.value.src_end - bulkForm.value.src_start + 1
  for (let i = 0; i < rangeSize; i++) {
    editorForm.value.mappings.push({
      src_universe: bulkForm.value.src_universe,
      src_channel: bulkForm.value.src_start + i,
      dst_universe: bulkForm.value.dst_universe,
      dst_channel: bulkForm.value.dst_start + i
    })
  }
}

// Visual editor functions
function isSourceMapped(universeId, channel) {
  return editorForm.value.mappings.some(
    m => m.src_universe === universeId && m.src_channel === channel
  )
}

function isDestMapped(universeId, channel) {
  return editorForm.value.mappings.some(
    m => m.dst_universe === universeId && m.dst_channel === channel
  )
}

function startDrag(channel) {
  dragSource.value = { universe: visualSourceUniverse.value, channel }
}

function endDrag() {
  dragSource.value = null
  dragOverDest.value = null
}

function dropOnDest(channel) {
  if (dragSource.value) {
    editorForm.value.mappings.push({
      src_universe: dragSource.value.universe,
      src_channel: dragSource.value.channel,
      dst_universe: visualDestUniverse.value,
      dst_channel: channel
    })
  }
  dragSource.value = null
  dragOverDest.value = null
}

onMounted(() => {
  loadMappings()
  loadUniverses()
})
</script>

<style scoped>
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-badge {
  padding: 4px 12px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
}

.status-badge.active {
  background: rgba(74, 222, 128, 0.2);
  color: var(--success);
}

/* Mapping configs list */
.mapping-configs {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 24px;
}

.configs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.configs-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.configs-list {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.config-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 8px;
  transition: all 0.2s;
}

.config-card.active {
  border-color: var(--success);
  background: rgba(74, 222, 128, 0.05);
}

.config-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.config-name {
  font-weight: 600;
  font-size: 15px;
}

.config-count {
  font-size: 12px;
  color: var(--text-secondary);
}

.config-actions {
  display: flex;
  gap: 8px;
}

.no-configs {
  text-align: center;
  color: var(--text-secondary);
  padding: 40px;
}

/* Modal styles */
.modal-large {
  max-width: 900px;
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  transition: max-width 0.2s ease;
}

.modal-large.modal-visual {
  max-width: 95vw;
  width: 95vw;
}

.editor-content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.editor-top {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 16px;
}

.radio-group {
  display: flex;
  gap: 16px;
}

.radio-option {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
  transition: all 0.15s;
}

.radio-option:hover {
  border-color: var(--accent);
}

.radio-option.selected {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  border-color: var(--accent);
}

/* Edit mode tabs */
.edit-mode-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 16px;
}

.tab-btn {
  padding: 10px 20px;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 14px;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: var(--text-primary);
}

.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* Table editor */
.table-editor {
  margin-bottom: 16px;
}

.table-container {
  max-height: 300px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 12px;
}

.mapping-table {
  width: 100%;
  border-collapse: collapse;
}

.mapping-table th,
.mapping-table td {
  padding: 10px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.mapping-table th {
  background: var(--bg-tertiary);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  color: var(--text-secondary);
  position: sticky;
  top: 0;
}

.mapping-table td input,
.mapping-table td select {
  width: 100%;
  min-width: 80px;
}

/* Bulk editor */
.bulk-editor {
  background: var(--bg-tertiary);
  padding: 16px;
  border-radius: 8px;
  margin-bottom: 16px;
}

.bulk-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}

.bulk-preview {
  display: flex;
  flex-direction: column;
}

.preview-text {
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-radius: 4px;
  font-family: monospace;
  color: var(--accent);
}

/* Visual editor */
.visual-editor {
  margin-bottom: 16px;
}

.visual-controls {
  display: flex;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.visual-control-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.visual-control-group label {
  font-size: 12px;
  color: var(--text-secondary);
}

.visual-control-group select,
.visual-control-group input {
  min-width: 100px;
}

.visual-control-group input[type="number"] {
  width: 80px;
}

.visual-grids {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.visual-grid-section {
  background: var(--bg-tertiary);
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.visual-grid-section h4 {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: var(--text-secondary);
}

.channel-grid {
  display: grid;
  gap: 2px;
  max-height: 400px;
  overflow: auto;
}

.channel-cell {
  padding: 4px 2px;
  text-align: center;
  font-size: 10px;
  background: var(--bg-secondary);
  border-radius: 2px;
  cursor: pointer;
  transition: all 0.15s;
  border: 1px solid transparent;
  min-width: 24px;
}

.channel-cell.source {
  cursor: grab;
}

.channel-cell.source:active {
  cursor: grabbing;
}

.channel-cell.destination {
  cursor: crosshair;
}

.channel-cell.mapped {
  background: rgba(74, 222, 128, 0.3);
  color: var(--success);
}

.channel-cell.dragging {
  opacity: 0.5;
  border-color: var(--accent);
}

.channel-cell.dragover {
  background: rgba(233, 69, 96, 0.3);
  border-color: var(--accent);
}

/* Mappings summary */
.mappings-summary {
  background: var(--bg-tertiary);
  padding: 16px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.mappings-summary h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
}

.summary-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.mapping-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 11px;
  font-family: monospace;
}

.chip-remove {
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  padding: 0 2px;
  font-size: 14px;
}

.chip-remove:hover {
  color: var(--error);
}

.more-count {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 4px 8px;
}

.no-mappings {
  color: var(--text-secondary);
  font-size: 13px;
}

.btn-success {
  background: var(--success);
  color: #000;
}

@media (max-width: 768px) {
  .editor-top {
    grid-template-columns: 1fr;
  }

  .bulk-row {
    grid-template-columns: 1fr;
  }

  .visual-grids {
    grid-template-columns: 1fr;
  }
}

/* Help button and modal styles */
.help-btn {
  width: 24px;
  height: 24px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  border-radius: 50%;
  margin-left: 8px;
  vertical-align: middle;
}

.help-content {
  padding: 8px 0;
  max-height: 65vh;
  overflow-y: auto;
}

.help-intro {
  color: var(--text-secondary);
  margin-bottom: 20px;
  line-height: 1.5;
}

.help-section {
  margin-bottom: 20px;
}

.help-section h4 {
  color: var(--accent);
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 600;
}

.help-section p {
  margin: 0 0 8px 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary);
}

.help-section ul {
  margin: 8px 0;
  padding-left: 20px;
  font-size: 13px;
  color: var(--text-primary);
}

.help-section li {
  margin-bottom: 6px;
}

.help-example {
  background: var(--bg-tertiary);
  border-left: 3px solid var(--accent);
  padding: 8px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  border-radius: 0 4px 4px 0;
}

.help-option {
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 8px;
}

.help-option-label {
  font-weight: 600;
  color: var(--text-primary);
  font-size: 13px;
  display: block;
  margin-bottom: 4px;
}

.help-option p {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>

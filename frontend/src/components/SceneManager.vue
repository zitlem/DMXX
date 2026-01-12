<template>
  <div>
    <div class="card-header" style="margin-bottom: 16px;">
      <h2 class="card-title">Scene Manager</h2>
      <button class="btn btn-primary" @click="openNewSceneModal">+ New Scene</button>
    </div>

    <!-- Info Note -->
    <div class="info-banner">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <span>Channels not included in a scene will remain unchanged when recalled. To turn a light off, include the channel with value 0.</span>
    </div>

    <!-- Scene List -->
    <div class="card">
      <table class="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Transition</th>
            <th>Duration</th>
            <th>Channels</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="scene in dmxStore.scenes" :key="scene.id">
            <td class="truncate-mobile">
              <strong>{{ scene.name }}</strong>
            </td>
            <td>
              <span class="transition-badge">{{ scene.transition_type }}</span>
            </td>
            <td>{{ scene.duration > 0 ? `${scene.duration}ms` : '-' }}</td>
            <td>{{ scene.values?.length || 0 }}</td>
            <td class="action-buttons">
              <button class="btn btn-small btn-primary" @click="recallScene(scene)">Recall</button>
              <button class="btn btn-small btn-secondary" @click="editScene(scene)">Edit</button>
              <button class="btn btn-small btn-secondary" @click="editSceneValues(scene)">Values</button>
              <button class="btn btn-small btn-secondary" @click="updateSceneValues(scene)">Update</button>
              <button class="btn btn-small btn-danger" @click="confirmDeleteScene(scene)">Delete</button>
            </td>
          </tr>
          <tr v-if="dmxStore.scenes.length === 0">
            <td colspan="5" style="text-align: center; color: var(--text-secondary); padding: 40px;">
              No scenes created yet. Click "+ New Scene" to create your first scene.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Add/Edit Scene Modal -->
    <div v-if="showAddScene || editingScene" class="modal-overlay">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingScene ? 'Edit Scene' : 'New Scene' }}</h3>
          <button class="modal-close" @click="closeSceneModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Scene Name</label>
          <input type="text" class="form-input" v-model="sceneForm.name" placeholder="e.g., Stage Wash">
        </div>

        <div class="form-group">
          <label class="form-label">Transition Type</label>
          <select class="form-select" v-model="sceneForm.transition_type">
            <option value="instant">Instant</option>
            <option value="fade">Fade</option>
            <option value="crossfade">Crossfade</option>
          </select>
        </div>

        <div v-if="sceneForm.transition_type !== 'instant'" class="form-group">
          <label class="form-label">Duration (ms)</label>
          <input type="number" class="form-input" v-model.number="sceneForm.duration" min="0" step="100" placeholder="1000">
        </div>

        <!-- Universe Selection (only for new scenes) -->
        <div v-if="!editingScene" class="form-group">
          <label class="form-label">Universes to Capture</label>
          <div class="universe-select-header">
            <button type="button" class="btn btn-small btn-secondary" @click="selectedUniverses = universes.map(u => u.id)">All</button>
            <button type="button" class="btn btn-small btn-secondary" @click="selectedUniverses = []">None</button>
            <button type="button" class="btn btn-small btn-secondary" @click="openJumpPopup('new')" v-if="universes.length > 4">Jump ▼</button>
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
                @change="toggleUniverse(u.id, selectedUniverses)"
              >
              <span class="checkbox-label">{{ u.label }}</span>
            </label>
          </div>
          <p v-if="selectedUniverses.length === 0" class="warning-text">
            Please select at least one universe
          </p>
        </div>

        <div v-if="!editingScene" class="form-group">
          <p style="color: var(--text-secondary); font-size: 13px;">
            This will save the current fader values from the selected universe(s) as a new scene.
          </p>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="closeSceneModal">Cancel</button>
          <button
            type="button"
            class="btn btn-primary"
            @click="saveScene"
            :disabled="!canSaveScene"
          >
            {{ editingScene ? 'Update' : 'Save Scene' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div v-if="deletingScene" class="modal-overlay">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">Delete Scene</h3>
          <button class="modal-close" @click="deletingScene = null">&times;</button>
        </div>
        <p>Are you sure you want to delete this scene?</p>
        <p style="color: var(--text-secondary);">{{ deletingScene.name }}</p>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="deletingScene = null">Cancel</button>
          <button type="button" class="btn btn-danger" @click="deleteScene">Delete</button>
        </div>
      </div>
    </div>

    <!-- Update Confirmation Modal -->
    <div v-if="updatingScene" class="modal-overlay">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">Update Scene Values</h3>
          <button class="modal-close" @click="updatingScene = null">&times;</button>
        </div>
        <p>Update "{{ updatingScene.name }}" with current fader values?</p>

        <!-- Universe Selection -->
        <div class="form-group" style="margin-top: 16px;">
          <label class="form-label">Universes to Update</label>
          <div class="universe-select-header">
            <button type="button" class="btn btn-small btn-secondary" @click="updateSelectedUniverses = universes.map(u => u.id)">All</button>
            <button type="button" class="btn btn-small btn-secondary" @click="updateSelectedUniverses = []">None</button>
            <button type="button" class="btn btn-small btn-secondary" @click="openJumpPopup('update')" v-if="universes.length > 4">Jump ▼</button>
          </div>
          <div class="universe-checkboxes">
            <label
              v-for="u in universes"
              :key="u.id"
              :data-universe-id="u.id"
              class="universe-checkbox"
              :class="{ selected: updateSelectedUniverses.includes(u.id) }"
            >
              <input
                type="checkbox"
                :checked="updateSelectedUniverses.includes(u.id)"
                @change="toggleUniverse(u.id, updateSelectedUniverses)"
              >
              <span class="checkbox-label">{{ u.label }}</span>
            </label>
          </div>
        </div>

        <!-- Merge Mode -->
        <div class="form-group">
          <label class="form-label">Update Mode</label>
          <div class="radio-group">
            <label class="radio-option">
              <input type="radio" v-model="updateMergeMode" value="replace_all">
              <span>Replace all values (remove other universes)</span>
            </label>
            <label class="radio-option">
              <input type="radio" v-model="updateMergeMode" value="replace">
              <span>Merge (keep other universes, update selected)</span>
            </label>
          </div>
        </div>

        <p style="color: var(--text-secondary); font-size: 13px; margin-top: 12px;">
          <template v-if="updateMergeMode === 'replace_all'">
            This will replace ALL scene values with values from the selected universe(s).
          </template>
          <template v-else>
            This will update only the selected universe(s), keeping existing values from other universes.
          </template>
        </p>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="updatingScene = null">Cancel</button>
          <button
            type="button"
            class="btn btn-primary"
            @click="confirmUpdateValues"
            :disabled="updateSelectedUniverses.length === 0"
          >Update Values</button>
        </div>
      </div>
    </div>

    <!-- Edit Values Modal -->
    <div v-if="editingValues" class="modal-overlay">
      <div class="modal modal-wide">
        <div class="modal-header">
          <h3 class="modal-title">Edit Values - {{ editingValues.name }}</h3>
          <button class="modal-close" @click="editingValues = null">&times;</button>
        </div>

        <div class="values-editor">
          <!-- Universe Tabs -->
          <div class="universe-tabs-row">
            <div class="universe-tabs">
              <button
                v-for="u in universes"
                :key="u.id"
                :data-universe-id="u.id"
                class="universe-tab"
                :class="{ active: activeValueTab === u.id }"
                @click="activeValueTab = u.id"
              >
                {{ u.label }} ({{ getValueCountForUniverse(u.id) }})
              </button>
            </div>
            <div class="universe-tabs-actions">
              <button type="button" class="btn btn-small btn-secondary" @click="openJumpPopup('values')" v-if="universes.length > 4">Jump ▼</button>
              <button
                type="button"
                class="btn btn-small btn-danger"
                @click="deleteUniverseValues(activeValueTab)"
                :disabled="getValueCountForUniverse(activeValueTab) === 0"
              >
                Delete Universe
              </button>
            </div>
          </div>

          <!-- Bulk Operations Section -->
          <div class="bulk-section">
            <div class="bulk-toggle">
              <button class="toggle-btn" :class="{ active: bulkMode === 'add' }" @click="bulkMode = 'add'">Add</button>
              <button class="toggle-btn" :class="{ active: bulkMode === 'delete' }" @click="bulkMode = 'delete'">Delete</button>
            </div>
            <span class="bulk-label">Ch</span>
            <input type="number" class="form-input bulk-input" v-model.number="bulkStart" min="1" max="512" placeholder="Start">
            <span>to</span>
            <input type="number" class="form-input bulk-input" v-model.number="bulkEnd" min="1" max="512" placeholder="End">
            <template v-if="bulkMode === 'add'">
              <span>@</span>
              <input type="number" class="form-input bulk-input" v-model.number="bulkValue" min="0" max="255" placeholder="255">
            </template>
            <button
              type="button"
              class="btn btn-small"
              :class="bulkMode === 'add' ? 'btn-primary' : 'btn-danger'"
              @click="executeBulkForActiveTab"
              :disabled="!bulkStart || !bulkEnd"
            >{{ bulkMode === 'add' ? 'Add' : 'Delete' }}</button>
          </div>

          <!-- Values for Selected Universe -->
          <div class="values-header values-header-tabbed">
            <span>Channel</span>
            <span>Value</span>
            <span></span>
          </div>
          <div class="values-list">
            <div
              v-for="val in getValuesForUniverse(activeValueTab)"
              :key="`${val.universe_id}-${val.channel}-${val.value}`"
              class="value-row value-row-tabbed"
            >
              <input type="number" class="form-input" v-model.number="val.channel" min="1" max="512">
              <input type="number" class="form-input" v-model.number="val.value" min="0" max="255">
              <button type="button" class="btn btn-small btn-danger" @click="removeValueByRef(val)">X</button>
            </div>
            <div v-if="getValuesForUniverse(activeValueTab).length === 0" style="padding: 20px; text-align: center; color: var(--text-secondary);">
              No values for this universe. Click "+ Add Channel" to add.
            </div>
          </div>
          <button type="button" class="btn btn-small btn-secondary" @click="addValueToUniverse(activeValueTab)" style="margin-top: 8px;">
            + Add Channel
          </button>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="editingValues = null">Cancel</button>
          <button type="button" class="btn btn-primary" @click="saveSceneValues">Save Values</button>
        </div>
      </div>
    </div>

    <!-- Jump Popup -->
    <div v-if="showJumpPopup" class="modal-overlay" @click.self="showJumpPopup = false">
      <div class="jump-popup">
        <div class="jump-popup-header">
          <h4>{{ jumpPopupMode === 'values' ? 'Jump to Universe' : 'Select Universe' }}</h4>
          <button class="modal-close" @click="showJumpPopup = false">&times;</button>
        </div>
        <div class="jump-popup-list">
          <button
            v-for="u in universes"
            :key="u.id"
            class="jump-popup-item"
            :class="{
              selected: jumpPopupMode === 'new' ? selectedUniverses.includes(u.id) :
                        jumpPopupMode === 'update' ? updateSelectedUniverses.includes(u.id) :
                        activeValueTab === u.id
            }"
            @click="jumpToUniverse(u.id)"
          >
            {{ u.label }}
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useDmxStore } from '../stores/dmx.js'
import { useAuthStore } from '../stores/auth.js'
import { wsManager } from '../websocket.js'

const dmxStore = useDmxStore()
const authStore = useAuthStore()

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

const showAddScene = ref(false)
const editingScene = ref(null)
const deletingScene = ref(null)
const updatingScene = ref(null)
const editingValues = ref(null)
const editValuesForm = ref([])
const { universes } = storeToRefs(dmxStore)
const bulkMode = ref('add')
const bulkStart = ref(null)
const bulkEnd = ref(null)
const bulkValue = ref(255)
const bulkUniverse = ref(1)

// Universe selection state
const selectedUniverses = ref([])  // For new scene modal
const updateSelectedUniverses = ref([])  // For update modal
const updateMergeMode = ref('replace_all')  // 'replace_all' or 'replace'
const activeValueTab = ref(1)  // For Edit Values modal

// Jump popup state
const showJumpPopup = ref(false)
const jumpPopupMode = ref('new')  // 'new', 'update', or 'values'

const sceneForm = ref({
  name: '',
  transition_type: 'instant',
  duration: 0
})

const canSaveScene = computed(() => {
  if (!sceneForm.value.name) return false
  if (!editingScene.value && selectedUniverses.value.length === 0) return false
  return true
})

onMounted(async () => {
  await dmxStore.loadScenes()
  await dmxStore.loadUniverses()
  initUniverseSelection()
})

// Universe selection helpers
function initUniverseSelection() {
  selectedUniverses.value = universes.value.map(u => u.id)
}

function initUpdateUniverseSelection(scene) {
  const sceneUniverseIds = [...new Set(scene.values?.map(v => v.universe_id) || [])]
  updateSelectedUniverses.value = sceneUniverseIds.length > 0
    ? sceneUniverseIds
    : universes.value.map(u => u.id)
}

function toggleUniverse(universeId, selectionArray) {
  const idx = selectionArray.indexOf(universeId)
  if (idx === -1) {
    selectionArray.push(universeId)
  } else {
    selectionArray.splice(idx, 1)
  }
}

// Jump popup helpers
function openJumpPopup(mode) {
  jumpPopupMode.value = mode
  showJumpPopup.value = true
}

function jumpToUniverse(universeId) {
  if (jumpPopupMode.value === 'values') {
    // For Edit Values tab mode - switch to that tab and scroll
    activeValueTab.value = universeId
    nextTick(() => {
      const tabEl = document.querySelector(`.universe-tabs button[data-universe-id="${universeId}"]`)
      if (tabEl) {
        tabEl.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
      }
    })
  } else {
    // For 'new' and 'update' modes - scroll to the checkbox
    const checkboxEl = document.querySelector(`[data-universe-id="${universeId}"]`)
    if (checkboxEl) {
      checkboxEl.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
    }
  }
  showJumpPopup.value = false
}

// Edit Values helpers
function getValuesForUniverse(universeId) {
  return editValuesForm.value.filter(v => v.universe_id === universeId)
    .sort((a, b) => a.channel - b.channel)
}

function getUniverseLabel(universeId) {
  const u = universes.value.find(u => u.id === universeId)
  return u ? u.label : `Universe ${universeId}`
}

function addValueToUniverse(universeId) {
  editValuesForm.value.push({
    universe_id: universeId,
    channel: 1,
    value: 255
  })
}

function removeValueByRef(val) {
  const idx = editValuesForm.value.findIndex(
    v => v.universe_id === val.universe_id && v.channel === val.channel && v.value === val.value
  )
  if (idx !== -1) {
    editValuesForm.value.splice(idx, 1)
  }
}

function getValueCountForUniverse(universeId) {
  return editValuesForm.value.filter(v => v.universe_id === universeId).length
}

function deleteUniverseValues(universeId) {
  const count = getValueCountForUniverse(universeId)
  if (count === 0) {
    alert(`No values for ${getUniverseLabel(universeId)}`)
    return
  }
  if (confirm(`Delete all ${count} values from ${getUniverseLabel(universeId)}?`)) {
    editValuesForm.value = editValuesForm.value.filter(v => v.universe_id !== universeId)
  }
}

function executeBulkForActiveTab() {
  const start = Math.min(bulkStart.value, bulkEnd.value)
  const end = Math.max(bulkStart.value, bulkEnd.value)
  const universeId = activeValueTab.value

  if (bulkMode.value === 'add') {
    const value = bulkValue.value ?? 255

    for (let ch = start; ch <= end; ch++) {
      if (!editValuesForm.value.find(v => v.channel === ch && v.universe_id === universeId)) {
        editValuesForm.value.push({
          universe_id: universeId,
          channel: ch,
          value: value
        })
      }
    }
    editValuesForm.value.sort((a, b) => a.universe_id - b.universe_id || a.channel - b.channel)
  } else {
    const count = editValuesForm.value.filter(
      v => v.universe_id === universeId && v.channel >= start && v.channel <= end
    ).length
    if (count === 0) {
      alert(`No channels found in range ${start}-${end} for ${getUniverseLabel(universeId)}`)
      return
    }
    if (confirm(`Delete ${count} channel(s) in range ${start}-${end}?`)) {
      editValuesForm.value = editValuesForm.value.filter(
        v => v.universe_id !== universeId || v.channel < start || v.channel > end
      )
    }
  }

  bulkStart.value = null
  bulkEnd.value = null
}

function editScene(scene) {
  editingScene.value = scene
  sceneForm.value = {
    name: scene.name,
    transition_type: scene.transition_type,
    duration: scene.duration
  }
}

async function openNewSceneModal() {
  if (universes.value.length === 0) {
    await dmxStore.loadUniverses()
  }
  initUniverseSelection()
  showAddScene.value = true
}

function closeSceneModal() {
  showAddScene.value = false
  editingScene.value = null
  sceneForm.value = { name: '', transition_type: 'instant', duration: 0 }
  initUniverseSelection()
}

async function saveScene() {
  console.log('saveScene called', {
    name: sceneForm.value.name,
    selectedUniverses: selectedUniverses.value,
    editingScene: editingScene.value
  })
  try {
    if (editingScene.value) {
      // Update existing scene metadata
      const response = await fetch(`/api/scenes/update/${editingScene.value.id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...authStore.getAuthHeaders()
        },
        body: JSON.stringify({
          name: sceneForm.value.name,
          transition_type: sceneForm.value.transition_type,
          duration: sceneForm.value.transition_type === 'instant' ? 0 : sceneForm.value.duration
        })
      })
      if (response.ok) {
        await dmxStore.loadScenes()
        closeSceneModal()
      }
    } else {
      // Create new scene with universe filter
      const universeFilter = selectedUniverses.value.length === universes.value.length
        ? null
        : selectedUniverses.value
      await dmxStore.createScene(
        sceneForm.value.name,
        sceneForm.value.transition_type,
        sceneForm.value.transition_type === 'instant' ? 0 : sceneForm.value.duration,
        universeFilter
      )
      closeSceneModal()
    }
  } catch (e) {
    console.error('Failed to save scene:', e)
  }
}

async function recallScene(scene) {
  try {
    dmxStore.startSceneRecallGracePeriod(scene.duration || 0)
    wsManager.setActiveScene(scene.id)
    await dmxStore.recallScene(scene.id)
  } catch (e) {
    console.error('Failed to recall scene:', e)
  }
}

function confirmDeleteScene(scene) {
  deletingScene.value = scene
}

async function deleteScene() {
  try {
    await dmxStore.deleteScene(deletingScene.value.id)
    deletingScene.value = null
  } catch (e) {
    console.error('Failed to delete scene:', e)
  }
}

function updateSceneValues(scene) {
  updatingScene.value = scene
  initUpdateUniverseSelection(scene)
  updateMergeMode.value = 'replace_all'
}

async function confirmUpdateValues() {
  try {
    const universeFilter = updateSelectedUniverses.value.length === universes.value.length
      ? null
      : updateSelectedUniverses.value
    await dmxStore.updateScene(
      updatingScene.value.id,
      universeFilter,
      updateMergeMode.value
    )
    updatingScene.value = null
  } catch (e) {
    console.error('Failed to update scene values:', e)
  }
}

// Edit Values functions
async function editSceneValues(scene) {
  try {
    const response = await fetchWithAuth(`/api/scenes/${scene.id}`)
    const freshScene = await response.json()
    editingValues.value = freshScene
    editValuesForm.value = freshScene.values ? freshScene.values.map(v => ({ ...v })) : []
    bulkUniverse.value = universes.value[0]?.id || 1
    // Set active tab to first universe with values, or first universe
    const universeWithValues = universes.value.find(u =>
      editValuesForm.value.some(v => v.universe_id === u.id)
    )
    activeValueTab.value = universeWithValues?.id || universes.value[0]?.id || 1
  } catch (e) {
    console.error('Failed to load scene:', e)
  }
}

function addValue() {
  editValuesForm.value.push({
    universe_id: universes.value[0]?.id || 1,
    channel: 1,
    value: 255
  })
}

function removeValue(idx) {
  editValuesForm.value.splice(idx, 1)
}

function executeBulk() {
  const start = Math.min(bulkStart.value, bulkEnd.value)
  const end = Math.max(bulkStart.value, bulkEnd.value)
  const universeId = bulkUniverse.value

  if (bulkMode.value === 'add') {
    const value = bulkValue.value ?? 255

    for (let ch = start; ch <= end; ch++) {
      if (!editValuesForm.value.find(v => v.channel === ch && v.universe_id === universeId)) {
        editValuesForm.value.push({
          universe_id: universeId,
          channel: ch,
          value: value
        })
      }
    }
    editValuesForm.value.sort((a, b) => a.universe_id - b.universe_id || a.channel - b.channel)
  } else {
    // Filter by selected universe for delete
    const count = editValuesForm.value.filter(
      v => v.universe_id === universeId && v.channel >= start && v.channel <= end
    ).length
    if (count === 0) {
      alert(`No channels found in range ${start}-${end} for ${getUniverseLabel(universeId)}`)
      return
    }
    if (confirm(`Delete ${count} channel(s) in range ${start}-${end} from ${getUniverseLabel(universeId)}?`)) {
      editValuesForm.value = editValuesForm.value.filter(
        v => v.universe_id !== universeId || v.channel < start || v.channel > end
      )
    }
  }

  bulkStart.value = null
  bulkEnd.value = null
}

async function saveSceneValues() {
  try {
    const response = await fetch(`/api/scenes/update/${editingValues.value.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...authStore.getAuthHeaders()
      },
      body: JSON.stringify({
        values: editValuesForm.value
      })
    })
    if (response.ok) {
      await dmxStore.loadScenes()
      editingValues.value = null
    }
  } catch (e) {
    console.error('Failed to save scene values:', e)
  }
}

</script>

<style scoped>
.info-banner {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: 6px;
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.info-banner svg {
  flex-shrink: 0;
  margin-top: 2px;
  color: var(--accent);
}

.action-buttons {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.transition-badge {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  font-size: 12px;
  text-transform: capitalize;
}

.modal-standard {
  width: 500px;
  max-width: 90vw;
}

.modal-wide {
  max-width: 700px;
  width: 90%;
  max-height: min(90vh, 660px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.values-editor {
  margin: 16px 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.values-header,
.value-row {
  display: grid;
  grid-template-columns: 1fr 80px 80px 40px;
  gap: 8px;
  align-items: center;
  padding: 8px 0;
}

.values-header {
  font-weight: 600;
  font-size: 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
}

.values-list {
  flex: 1;
  overflow-y: auto;
  height: 280px;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
  padding-right: 20px;
}

.values-list::-webkit-scrollbar {
  width: 8px;
}

.values-list::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.values-list::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 4px;
  border: 2px solid transparent;
  background-clip: padding-box;
}

.values-list::-webkit-scrollbar-thumb:hover {
  background: var(--text-secondary);
  background-clip: padding-box;
}

.value-row input,
.value-row select {
  width: 100%;
}

.bulk-section {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  margin-bottom: 8px;
  font-size: 13px;
  flex-wrap: wrap;
}

.bulk-toggle {
  display: flex;
  background: var(--bg-primary);
  border-radius: 4px;
  overflow: hidden;
}

.toggle-btn {
  padding: 4px 8px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
}

.toggle-btn.active {
  background: var(--accent);
  color: white;
}

.bulk-input {
  width: 70px;
  min-width: 70px;
}

.bulk-label {
  color: var(--text-secondary);
  font-size: 12px;
}

/* Universe tabs row for Edit Values */
.universe-tabs-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
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
  background: rgba(233, 69, 96, 0.2);
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

/* Radio group for merge mode */
.radio-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.radio-option {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 13px;
}

.radio-option input[type="radio"] {
  accent-color: var(--accent);
}

/* Adjust values grid for tabbed view (2 columns) */
.values-header-tabbed,
.value-row-tabbed {
  display: grid;
  grid-template-columns: 80px 80px 36px;
  gap: 8px;
  align-items: center;
  padding: 8px 0;
}

.values-header-tabbed {
  font-weight: 600;
  font-size: 12px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
}

/* Universe tabs actions container */
.universe-tabs-actions {
  display: flex;
  gap: 8px;
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
</style>

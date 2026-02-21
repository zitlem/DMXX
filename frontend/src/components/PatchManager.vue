<template>
  <div>
    <div class="card-header" style="margin-bottom: 16px;">
      <h2 class="card-title">Patch Manager</h2>
      <button class="btn btn-primary" @click="showAddPatch = true">+ Add Patch</button>
    </div>

    <!-- Overlap Warning -->
    <div v-if="overlappingPatches.length > 0" class="overlap-warning">
      <strong>Channel Overlap Warning:</strong>
      <ul>
        <li v-for="(overlap, idx) in overlappingPatches" :key="idx">
          {{ overlap.patch1 }} ({{ overlap.range1 }}) overlaps with {{ overlap.patch2 }} ({{ overlap.range2 }})
        </li>
      </ul>
    </div>

    <!-- Patch List -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Patches</h3>
        <select class="form-select" style="width: auto;" v-model="filterUniverse">
          <option :value="null">All Universes</option>
          <option v-for="u in dmxStore.universes" :key="u.id" :value="u.id">{{ u.label }}</option>
        </select>
      </div>
      <table class="data-table">
        <thead>
          <tr>
            <th class="drag-col"></th>
            <th>Label</th>
            <th>Fixture</th>
            <th>Universe</th>
            <th>Channels</th>
            <th>Actions</th>
          </tr>
        </thead>
        <draggable
          v-model="dmxStore.patches"
          tag="tbody"
          item-key="id"
          :animation="200"
          ghost-class="patch-row-ghost"
          drag-class="patch-row-dragging"
          handle=".drag-handle"
          :delay="150"
          :delay-on-touch-only="true"
          :touch-start-threshold="5"
          filter=".action-buttons"
          :prevent-on-filter="false"
          @end="onDragEnd"
        >
          <template #item="{ element: patch }">
            <tr v-show="filterUniverse === null || patch.universe_id === filterUniverse">
              <td class="drag-handle">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="9" cy="6" r="2"/><circle cx="15" cy="6" r="2"/>
                  <circle cx="9" cy="12" r="2"/><circle cx="15" cy="12" r="2"/>
                  <circle cx="9" cy="18" r="2"/><circle cx="15" cy="18" r="2"/>
                </svg>
              </td>
              <td>{{ patch.label || '-' }}</td>
              <td>{{ patch.fixture_name }}</td>
              <td>{{ patch.universe_label }}</td>
              <td>{{ patch.start_channel }}-{{ patch.end_channel }}</td>
              <td class="action-buttons">
                <button class="btn btn-small btn-secondary" @click="editPatch(patch)">Edit</button>
                <button class="btn btn-small btn-danger" @click="confirmDeletePatch(patch)">Delete</button>
              </td>
            </tr>
          </template>
          <template #footer>
            <tr v-if="filteredPatches.length === 0">
              <td colspan="6" style="text-align: center; color: var(--text-secondary);">
                No patches configured
              </td>
            </tr>
          </template>
        </draggable>
      </table>
    </div>

    <!-- Add/Edit Patch Modal -->
    <div v-if="showAddPatch || editingPatch" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingPatch ? 'Edit Patch' : 'Add Patch' }}</h3>
          <button class="modal-close" @click="closePatchModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Label (optional)</label>
          <input type="text" class="form-input" v-model="patchForm.label" placeholder="e.g., Front Wash 1">
        </div>

        <div class="form-group">
          <label class="form-label">Fixture</label>
          <select class="form-select" v-model="patchForm.fixture_id">
            <option :value="null">Select fixture...</option>
            <option v-for="f in dmxStore.fixtures" :key="f.id" :value="f.id">
              {{ f.name }} ({{ f.channel_count }} ch)
            </option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">Universe</label>
          <select class="form-select" v-model="patchForm.universe_id">
            <option :value="null">Select universe...</option>
            <option v-for="u in dmxStore.universes" :key="u.id" :value="u.id">
              {{ u.label }}
            </option>
          </select>
        </div>

        <div class="form-group">
          <label class="form-label">Start Channel</label>
          <input type="number" class="form-input" v-model.number="patchForm.start_channel" min="1" max="512">
        </div>

        <div class="form-group">
          <label class="form-label">Group Color</label>
          <div style="display: flex; align-items: center; gap: 8px;">
            <input type="color" v-model="patchForm.group_color" style="width: 50px; height: 32px; border: none; cursor: pointer;">
            <span style="font-size: 11px; color: var(--text-secondary);">Stripe at bottom of faders to group this patch</span>
            <button v-if="patchForm.group_color" class="btn btn-small btn-secondary" @click="patchForm.group_color = ''" style="padding: 2px 6px;">Clear</button>
          </div>
        </div>

        <div v-if="patchError" class="alert alert-error">{{ patchError }}</div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closePatchModal">Cancel</button>
          <button class="btn btn-primary" @click="savePatch" :disabled="!canSavePatch">
            {{ editingPatch ? 'Update' : 'Add' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <div v-if="deletingPatch" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Delete Patch</h3>
          <button class="modal-close" @click="deletingPatch = null">&times;</button>
        </div>
        <p>Are you sure you want to delete this patch?</p>
        <p style="color: var(--text-secondary);">{{ deletingPatch.fixture_name }} @ {{ deletingPatch.universe_label }} Ch {{ deletingPatch.start_channel }}</p>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="deletingPatch = null">Cancel</button>
          <button class="btn btn-danger" @click="deletePatch">Delete</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import draggable from 'vuedraggable'
import { useDmxStore } from '../stores/dmx.js'
import { useAuthStore } from '../stores/auth.js'

const dmxStore = useDmxStore()
const authStore = useAuthStore()

const filterUniverse = ref(null)
const showAddPatch = ref(false)
const editingPatch = ref(null)
const deletingPatch = ref(null)
const patchError = ref('')

const patchForm = ref({
  label: '',
  fixture_id: null,
  universe_id: null,
  start_channel: 1,
  group_color: ''
})

const filteredPatches = computed(() => {
  if (filterUniverse.value === null) {
    return dmxStore.patches
  }
  return dmxStore.patches.filter(p => p.universe_id === filterUniverse.value)
})

const canSavePatch = computed(() => {
  return patchForm.value.fixture_id && patchForm.value.universe_id && patchForm.value.start_channel
})

const overlappingPatches = computed(() => {
  const overlaps = []
  const patches = filteredPatches.value

  for (let i = 0; i < patches.length; i++) {
    for (let j = i + 1; j < patches.length; j++) {
      const a = patches[i]
      const b = patches[j]

      // Only check within same universe
      if (a.universe_id !== b.universe_id) continue

      // Check if ranges overlap
      if (!(a.end_channel < b.start_channel || a.start_channel > b.end_channel)) {
        overlaps.push({
          patch1: a.label || a.fixture_name,
          patch2: b.label || b.fixture_name,
          range1: `${a.start_channel}-${a.end_channel}`,
          range2: `${b.start_channel}-${b.end_channel}`
        })
      }
    }
  }
  return overlaps
})

onMounted(async () => {
  await Promise.all([
    dmxStore.loadUniverses(),
    dmxStore.loadPatches(),
    dmxStore.loadFixtures()
  ])
})

async function onDragEnd(event) {
  // Only process if position actually changed
  if (event.oldIndex === event.newIndex) return

  // Extract ordered IDs from the patches array
  const orderedIds = dmxStore.patches.map(p => p.id)

  try {
    await fetch('/api/patch/reorder', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...authStore.getAuthHeaders()
      },
      body: JSON.stringify({ patch_ids: orderedIds })
    })
  } catch (e) {
    console.error('Failed to reorder patches:', e)
    // Reload patches to restore server state on error
    await dmxStore.loadPatches()
  }
}

function editPatch(patch) {
  editingPatch.value = patch
  patchForm.value = {
    label: patch.label,
    fixture_id: patch.fixture_id,
    universe_id: patch.universe_id,
    start_channel: patch.start_channel,
    group_color: patch.group_color || ''
  }
  patchError.value = ''
}

function closePatchModal() {
  showAddPatch.value = false
  editingPatch.value = null
  patchForm.value = { label: '', fixture_id: null, universe_id: null, start_channel: 1, group_color: '' }
  patchError.value = ''
}

async function savePatch() {
  patchError.value = ''

  try {
    const url = editingPatch.value
      ? `/api/patch/${editingPatch.value.id}`
      : '/api/patch'
    const method = editingPatch.value ? 'PUT' : 'POST'

    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...authStore.getAuthHeaders()
      },
      body: JSON.stringify(patchForm.value)
    })

    if (response.ok) {
      await dmxStore.loadPatches()
      closePatchModal()
    } else {
      const error = await response.json()
      patchError.value = error.detail || 'Failed to save patch'
    }
  } catch (e) {
    patchError.value = 'Failed to save patch'
  }
}

function confirmDeletePatch(patch) {
  deletingPatch.value = patch
}

async function deletePatch() {
  try {
    await fetch(`/api/patch/${deletingPatch.value.id}`, {
      method: 'DELETE',
      headers: authStore.getAuthHeaders()
    })
    await dmxStore.loadPatches()
  } catch (e) {
    console.error('Failed to delete patch:', e)
  }
  deletingPatch.value = null
}

</script>

<style scoped>
/* Drag-and-drop styles */
.patch-row-ghost {
  opacity: 0.4;
  background: var(--bg-secondary);
}

.patch-row-dragging {
  opacity: 0.9;
  background: var(--bg-tertiary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

/* Drag handle column */
.drag-col {
  width: 36px;
}

.drag-handle {
  width: 36px;
  padding: 8px !important;
  cursor: grab;
  color: var(--text-secondary);
  text-align: center;
  touch-action: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-handle svg {
  opacity: 0.4;
  transition: opacity 0.2s;
}

.drag-handle:hover svg,
tr:hover .drag-handle svg {
  opacity: 0.8;
}

.action-buttons {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  touch-action: manipulation;
}

.action-buttons .btn {
  touch-action: manipulation;
}

.overlap-warning {
  background: rgba(245, 158, 11, 0.15);
  border: 1px solid #f59e0b;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 16px;
  color: #f59e0b;
}

.overlap-warning ul {
  margin: 8px 0 0 0;
  padding-left: 20px;
}

.overlap-warning li {
  margin: 4px 0;
}
</style>

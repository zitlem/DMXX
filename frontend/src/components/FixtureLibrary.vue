<template>
  <div>
    <div class="card-header" style="margin-bottom: 16px;">
      <h2 class="card-title">Fixture Library</h2>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-secondary" @click="showImport = true">Import OFL</button>
        <button class="btn btn-primary" @click="showCreate = true">+ Create Fixture</button>
      </div>
    </div>

    <!-- Fixture list -->
    <div class="card">
      <table class="data-table">
        <thead>
          <tr>
            <th>Name</th>
            <th><span class="hide-mobile">Manufacturer</span><span class="show-mobile">Manuf</span></th>
            <th>Channels</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="fixture in dmxStore.fixtures" :key="fixture.id">
            <td>{{ fixture.name }}</td>
            <td>{{ fixture.manufacturer || '-' }}</td>
            <td>{{ fixture.channel_count }}</td>
            <td class="action-buttons">
              <button class="btn btn-small btn-secondary" @click="viewFixture(fixture)">View</button>
              <button class="btn btn-small btn-secondary" @click="editFixture(fixture)">Edit</button>
              <button class="btn btn-small btn-secondary" @click="confirmDuplicate(fixture)">Duplicate</button>
              <button class="btn btn-small btn-danger" @click="confirmDelete(fixture)">Delete</button>
            </td>
          </tr>
          <tr v-if="dmxStore.fixtures.length === 0">
            <td colspan="4" style="text-align: center; color: var(--text-secondary);">
              No fixtures in library. Create a fixture or import from Open Fixture Library.
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- View Fixture Modal -->
    <div v-if="viewingFixture" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">{{ viewingFixture.name }}</h3>
          <button class="modal-close" @click="viewingFixture = null">&times;</button>
        </div>
        <div style="margin-bottom: 12px;">
          <span style="color: var(--text-secondary);">Manufacturer:</span>
          {{ viewingFixture.manufacturer || 'Unknown' }}
        </div>
        <div style="margin-bottom: 16px;">
          <span style="color: var(--text-secondary);">Channels:</span>
          {{ viewingFixture.channel_count }}
        </div>
        <table class="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Name</th>
              <th>Type</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(channel, index) in viewingFixture.channels" :key="index">
              <td>{{ index + 1 }}</td>
              <td>{{ channel.name }}</td>
              <td>{{ channel.type }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Create/Edit Fixture Modal -->
    <div v-if="showCreate" class="modal-overlay">
      <div class="modal" style="max-width: 700px;">
        <div class="modal-header">
          <h3 class="modal-title">{{ editingFixtureId ? 'Edit Fixture' : 'Create Fixture' }}</h3>
          <button class="modal-close" @click="closeCreateModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Fixture Name</label>
          <input type="text" class="form-input" v-model="newFixture.name" placeholder="e.g., My Par Can">
        </div>

        <div class="form-group">
          <label class="form-label">Manufacturer</label>
          <input type="text" class="form-input" v-model="newFixture.manufacturer" placeholder="e.g., Generic">
        </div>

        <div style="margin-bottom: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <label class="form-label" style="margin: 0;">Channels</label>
            <button class="btn btn-small btn-secondary" @click="addChannel">+ Add Channel</button>
          </div>
          <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 12px; line-height: 1.4;">
            <strong>Intensity</strong> = brightness/dimmer.
            <strong>Color</strong> = RGB/RGBW mixing.
            <strong>Pan/Tilt</strong> = moving head position.
            <strong>Gobo</strong> = pattern wheel.
            <strong>Shutter</strong> = strobe.
            <strong>Other</strong> = everything else.
            Fader color auto-suggests from channel name.
          </div>
          <div v-for="(channel, index) in newFixture.channels" :key="index" style="display: flex; gap: 8px; margin-bottom: 8px; align-items: center;">
            <input
              type="text"
              class="form-input"
              v-model="channel.name"
              @input="suggestChannelColor(channel)"
              placeholder="Channel name"
              style="flex: 1;"
            >
            <input
              type="text"
              class="form-input"
              v-model="channel.faderName"
              placeholder="Fader"
              title="Short label for fader display"
              style="width: 50px;"
            >
            <select class="form-select" v-model="channel.type" style="width: 110px;">
              <option value="intensity">Intensity</option>
              <option value="color">Color</option>
              <option value="pan">Pan</option>
              <option value="tilt">Tilt</option>
              <option value="gobo">Gobo</option>
              <option value="shutter">Shutter</option>
              <option value="other">Other</option>
            </select>
            <input
              type="color"
              v-model="channel.color"
              title="Fader color"
              style="width: 36px; height: 28px; border: none; cursor: pointer; padding: 0;"
            >
            <button class="btn btn-small btn-danger" @click="removeChannel(index)">X</button>
          </div>
        </div>

        <div class="modal-footer">
          <button class="btn btn-secondary" @click="closeCreateModal">Cancel</button>
          <button class="btn btn-primary" @click="saveFixture" :disabled="!canCreate">
            {{ editingFixtureId ? 'Save' : 'Create' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Import Modal -->
    <div v-if="showImport" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Import from Open Fixture Library</h3>
          <button class="modal-close" @click="showImport = false">&times;</button>
        </div>
        <p style="margin-bottom: 12px; color: var(--text-secondary);">
          Upload a JSON file from the
          <a href="https://open-fixture-library.org/" target="_blank" style="color: var(--accent);">Open Fixture Library</a>
        </p>
        <p style="margin-bottom: 16px; font-size: 12px; color: var(--text-secondary);">
          Expected format: OFL JSON with <code style="background: var(--bg-tertiary); padding: 1px 4px; border-radius: 3px;">name</code>,
          <code style="background: var(--bg-tertiary); padding: 1px 4px; border-radius: 3px;">availableChannels</code>, and
          <code style="background: var(--bg-tertiary); padding: 1px 4px; border-radius: 3px;">modes</code> fields.
          Download fixture files directly from OFL website.
        </p>
        <div class="form-group">
          <input type="file" accept=".json" @change="handleFileUpload" ref="fileInput">
        </div>
        <div v-if="importError" class="alert alert-error">{{ importError }}</div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showImport = false">Cancel</button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation -->
    <div v-if="deletingFixture" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Delete Fixture</h3>
          <button class="modal-close" @click="deletingFixture = null">&times;</button>
        </div>
        <p>Are you sure you want to delete "{{ deletingFixture.name }}"?</p>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="deletingFixture = null">Cancel</button>
          <button class="btn btn-danger" @click="deleteFixture">Delete</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useDmxStore } from '../stores/dmx.js'
import { useAuthStore } from '../stores/auth.js'

const dmxStore = useDmxStore()
const authStore = useAuthStore()

const showCreate = ref(false)
const showImport = ref(false)
const viewingFixture = ref(null)
const deletingFixture = ref(null)
const importError = ref('')
const editingFixtureId = ref(null)

// Color name to hex mapping for auto-suggest
const colorMap = {
  red: '#ff0000',
  green: '#00ff00',
  blue: '#0000ff',
  white: '#ffffff',
  amber: '#ffbf00',
  cyan: '#00ffff',
  magenta: '#ff00ff',
  yellow: '#ffff00',
  uv: '#8b00ff',
  ultraviolet: '#8b00ff',
  warm: '#ffd700',
  cool: '#87ceeb',
  orange: '#ff8000',
  pink: '#ff69b4',
  lime: '#32cd32'
}

const defaultFixture = () => ({
  name: '',
  manufacturer: '',
  channels: [{ name: 'Dimmer', type: 'intensity', color: '#888888', faderName: '' }]
})

const newFixture = ref(defaultFixture())

const canCreate = computed(() => {
  return newFixture.value.name && newFixture.value.channels.length > 0
})

onMounted(async () => {
  await dmxStore.loadFixtures()
})

function addChannel() {
  newFixture.value.channels.push({ name: '', type: 'intensity', color: '#888888', faderName: '' })
}

function removeChannel(index) {
  newFixture.value.channels.splice(index, 1)
}

function suggestChannelColor(channel) {
  const name = channel.name.toLowerCase()
  for (const [key, color] of Object.entries(colorMap)) {
    if (name.includes(key)) {
      channel.color = color
      return
    }
  }
}

function editFixture(fixture) {
  editingFixtureId.value = fixture.id
  // Use fixture.channels directly (already unpacked by API)
  const channels = fixture.channels || []
  newFixture.value = {
    name: fixture.name,
    manufacturer: fixture.manufacturer || '',
    channels: channels.map(ch => ({
      name: ch.name || '',
      type: ch.type || 'intensity',
      color: ch.color || '#888888',
      faderName: ch.faderName || ''
    }))
  }
  if (newFixture.value.channels.length === 0) {
    newFixture.value.channels = [{ name: 'Dimmer', type: 'intensity', color: '#888888', faderName: '' }]
  }
  showCreate.value = true
}

function closeCreateModal() {
  showCreate.value = false
  editingFixtureId.value = null
  newFixture.value = defaultFixture()
}

async function saveFixture() {
  try {
    const method = editingFixtureId.value ? 'PUT' : 'POST'
    const url = editingFixtureId.value
      ? `/api/fixtures/${editingFixtureId.value}`
      : '/api/fixtures'

    const response = await fetch(url, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...authStore.getAuthHeaders()
      },
      body: JSON.stringify({
        name: newFixture.value.name,
        manufacturer: newFixture.value.manufacturer,
        definition_json: {
          channels: newFixture.value.channels
        }
      })
    })

    if (response.ok) {
      await dmxStore.loadFixtures()
      closeCreateModal()
    }
  } catch (e) {
    console.error('Failed to save fixture:', e)
  }
}

async function handleFileUpload(event) {
  const file = event.target.files[0]
  if (!file) return

  importError.value = ''

  try {
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch('/api/fixtures/import/ofl', {
      method: 'POST',
      headers: authStore.getAuthHeaders(),
      body: formData
    })

    if (response.ok) {
      await dmxStore.loadFixtures()
      showImport.value = false
    } else {
      const error = await response.json()
      importError.value = error.detail || 'Import failed'
    }
  } catch (e) {
    importError.value = 'Failed to import file'
  }
}

function viewFixture(fixture) {
  viewingFixture.value = fixture
}

function confirmDelete(fixture) {
  deletingFixture.value = fixture
}

async function deleteFixture() {
  try {
    const response = await fetch(`/api/fixtures/${deletingFixture.value.id}`, {
      method: 'DELETE',
      headers: authStore.getAuthHeaders()
    })

    if (response.ok) {
      await dmxStore.loadFixtures()
    } else {
      const error = await response.json()
      alert(error.detail || 'Delete failed')
    }
  } catch (e) {
    console.error('Failed to delete fixture:', e)
  }

  deletingFixture.value = null
}

function confirmDuplicate(fixture) {
  // Open the create modal pre-filled with fixture data (as a new fixture)
  editingFixtureId.value = null  // Not editing, creating new
  const channels = fixture.channels || []
  newFixture.value = {
    name: `${fixture.name} (Copy)`,
    manufacturer: fixture.manufacturer || '',
    channels: channels.map(ch => ({
      name: ch.name || '',
      type: ch.type || 'intensity',
      color: ch.color || '#888888',
      faderName: ch.faderName || ''
    }))
  }
  if (newFixture.value.channels.length === 0) {
    newFixture.value.channels = [{ name: 'Dimmer', type: 'intensity', color: '#888888', faderName: '' }]
  }
  showCreate.value = true
}
</script>

<style scoped>
.action-buttons {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
</style>

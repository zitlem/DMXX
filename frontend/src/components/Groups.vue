<template>
  <div class="groups-page" :class="{ 'edit-mode-active': editMode }">
    <!-- Header -->
    <div class="card-header">
      <h2 class="card-title">Groups / Masters</h2>
      <div class="header-actions" v-if="authStore.isAdmin">
        <label class="edit-mode-toggle">
          <input type="checkbox" v-model="editMode">
          <span>Edit Mode</span>
        </label>
        <button class="btn btn-primary" @click="openNewGroupModal">+ Add Group</button>
      </div>
    </div>

    <!-- Info Note -->
    <div class="info-banner" v-if="groups.length === 0">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <span>No groups created yet. <strong v-if="authStore.isAdmin">Click "+ Add Group" to create your first group.</strong></span>
    </div>

    <!-- Main Layout -->
    <div class="groups-layout">
      <!-- Groups Grid -->
      <div class="groups-grid-container">
        <div class="groups-grid">
          <div
            v-for="group in groups"
            :key="group.id"
            class="group-fader"
            :class="{
              selected: editMode && selectedGroup?.id === group.id,
              disabled: !group.enabled
            }"
            @click="editMode && selectGroup(group)"
          >
            <span class="group-name" :title="group.name">{{ group.name }}</span>
            <div
              class="fader-track"
              @mousedown="startDrag($event, group)"
              @touchstart="startDrag($event, group)"
            >
              <div
                class="fader-fill"
                :style="{ height: (groupValues[group.id] || 0) / 255 * 100 + '%', background: group.color || 'var(--accent)' }"
              ></div>
            </div>
            <span class="group-value">{{ Math.round((groupValues[group.id] || 0) / 255 * 100) }}%</span>
            <div class="badge-row">
              <span class="mode-badge" :class="group.mode">{{ group.mode === 'proportional' ? 'P' : 'F' }}</span>
              <span v-if="group.master_channel" class="dmx-input-badge"
                :title="`Controlled by Universe ${group.master_universe} Channel ${group.master_channel}`">
                {{ group.master_universe }}.{{ group.master_channel }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Edit Panel (right sidebar, admin only) -->
      <div v-if="editMode && selectedGroup" class="edit-panel">
        <div class="edit-panel-header">
          <h3>Edit Group</h3>
          <button class="modal-close" @click="selectedGroup = null">&times;</button>
        </div>

        <div class="edit-panel-content">
          <div class="form-group">
            <label class="form-label">Name</label>
            <input
              type="text"
              class="form-input"
              v-model="editForm.name"
              @change="saveGroupChanges"
            >
          </div>

          <div class="form-group">
            <label class="form-label">Mode</label>
            <select class="form-select" v-model="editForm.mode" @change="saveGroupChanges">
              <option value="proportional">Proportional</option>
              <option value="follow">Follow</option>
            </select>
          </div>

          <div class="form-group">
            <label class="checkbox-label">
              <input type="checkbox" v-model="editForm.enabled" @change="saveGroupChanges">
              <span>Enabled</span>
            </label>
          </div>

          <div class="form-group">
            <label class="form-label">Fader Color</label>
            <div class="color-input-wrapper">
              <input
                type="color"
                :value="editForm.color || '#e94560'"
                @input="editForm.color = $event.target.value; saveGroupChanges()"
              >
              <input
                type="text"
                class="form-input color-hex"
                :value="editForm.color || ''"
                @change="editForm.color = $event.target.value || null; saveGroupChanges()"
                placeholder="Default"
              >
              <button
                v-if="editForm.color"
                class="btn btn-small btn-secondary"
                @click="editForm.color = null; saveGroupChanges()"
                title="Reset to default"
              >Reset</button>
            </div>
          </div>

          <!-- DMX Input Link (optional) -->
          <div class="input-link-section">
            <h4>DMX Input Link (Optional)</h4>
            <p class="help-text">Link this group to a DMX input channel. When input arrives on this channel, it will control the group master.</p>
            <div class="input-link-row">
              <div class="form-group">
                <label class="form-label">Universe</label>
                <select class="form-select" v-model.number="editForm.master_universe" @change="saveGroupChanges">
                  <option :value="null">None</option>
                  <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">Channel</label>
                <input
                  type="number"
                  class="form-input"
                  v-model.number="editForm.master_channel"
                  :disabled="!editForm.master_universe"
                  min="1"
                  max="512"
                  placeholder="1-512"
                  @change="saveGroupChanges"
                >
              </div>
            </div>
          </div>

          <!-- Members Section -->
          <div class="members-section">
            <div class="members-header">
              <h4>Members ({{ selectedGroup.members?.length || 0 }})</h4>
              <div class="members-header-buttons">
                <button
                  v-if="editForm.mode === 'proportional' && selectedGroup.members?.length > 0"
                  class="btn btn-small btn-secondary"
                  @click="showBulkBaseEdit = true"
                >Set All Base</button>
                <button class="btn btn-small btn-secondary" @click="openBulkAddModal">Bulk Add</button>
              </div>
            </div>

            <!-- Bulk Base Edit Control -->
            <div v-if="showBulkBaseEdit && editForm.mode === 'proportional'" class="bulk-base-edit">
              <label>Set all base values to:</label>
              <input type="number" class="form-input" v-model.number="bulkBaseValue" min="0" max="255">
              <button class="btn btn-small btn-primary" @click="applyBulkBaseValue">Apply</button>
              <button class="btn btn-small btn-secondary" @click="showBulkBaseEdit = false">Cancel</button>
            </div>

            <!-- Add Member -->
            <div class="add-member-row">
              <select class="form-select" v-model.number="newMember.universe_id">
                <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
              </select>
              <input
                type="number"
                class="form-input"
                v-model.number="newMember.channel"
                min="1"
                max="512"
                placeholder="Ch"
              >
              <input
                v-if="editForm.mode === 'proportional'"
                type="number"
                class="form-input"
                v-model.number="newMember.base_value"
                min="0"
                max="255"
                placeholder="Base"
              >
              <button class="btn btn-small btn-primary" @click="addMember" :disabled="!canAddMember">+</button>
            </div>

            <!-- Members List -->
            <div class="members-list">
              <div v-for="member in selectedGroup.members" :key="member.id" class="member-row">
                <span class="member-info">
                  <span class="member-channel">U{{ member.universe_id }}.{{ member.channel }}</span>
                  <span v-if="getMemberLabel(member)" class="member-label" :title="dmxStore.getChannelLabel(member.universe_id, member.channel)">{{ getMemberLabel(member) }}</span>
                </span>
                <template v-if="editForm.mode === 'proportional'">
                  <input
                    v-if="editingMember === member.id"
                    type="number"
                    class="form-input member-base-input"
                    v-model.number="editMemberValue"
                    min="0"
                    max="255"
                    @blur="saveMemberEdit(member)"
                    @keyup.enter="saveMemberEdit(member)"
                    @keyup.escape="cancelMemberEdit"
                  >
                  <span
                    v-else
                    class="member-base editable"
                    @click="startMemberEdit(member)"
                    title="Click to edit"
                  >@{{ member.base_value }}</span>
                </template>
                <button class="btn btn-small btn-danger" @click="removeMember(member)">X</button>
              </div>
              <div v-if="!selectedGroup.members?.length" class="no-members">
                No members yet
              </div>
            </div>
          </div>

          <!-- Delete Button -->
          <div class="danger-zone">
            <button class="btn btn-danger" @click="confirmDeleteGroup">Delete Group</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Add/Edit Group Modal -->
    <div v-if="showAddGroup" class="modal-overlay" @click.self="closeGroupModal">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">New Group</h3>
          <button class="modal-close" @click="closeGroupModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Group Name</label>
          <input type="text" class="form-input" v-model="groupForm.name" placeholder="e.g., Stage Dimmers">
        </div>

        <div class="form-group">
          <label class="form-label">Mode</label>
          <select class="form-select" v-model="groupForm.mode">
            <option value="proportional">Proportional (scales member base values)</option>
            <option value="follow">Follow (all members match master)</option>
          </select>
        </div>

        <div class="form-group">
          <label class="checkbox-label">
            <input type="checkbox" v-model="groupForm.enabled">
            <span>Enabled</span>
          </label>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="closeGroupModal">Cancel</button>
          <button
            type="button"
            class="btn btn-primary"
            @click="createGroup"
            :disabled="!canCreateGroup"
          >
            Create Group
          </button>
        </div>
      </div>
    </div>

    <!-- Delete Confirmation Modal -->
    <div v-if="deletingGroup" class="modal-overlay" @click.self="deletingGroup = null">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">Delete Group</h3>
          <button class="modal-close" @click="deletingGroup = null">&times;</button>
        </div>
        <p>Are you sure you want to delete this group?</p>
        <p style="color: var(--text-secondary);">{{ deletingGroup.name }}</p>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="deletingGroup = null">Cancel</button>
          <button type="button" class="btn btn-danger" @click="deleteGroup">Delete</button>
        </div>
      </div>
    </div>

    <!-- Bulk Add Modal -->
    <div v-if="showBulkAdd" class="modal-overlay" @click.self="closeBulkAddModal">
      <div class="modal modal-bulk-add">
        <div class="modal-header">
          <h3 class="modal-title">Select Channels to Add</h3>
          <button class="modal-close" @click="closeBulkAddModal">&times;</button>
        </div>

        <div class="bulk-add-controls">
          <div class="bulk-add-row">
            <div class="form-group">
              <label class="form-label">Universe</label>
              <select class="form-select" v-model.number="bulkAdd.universe_id" @change="onBulkUniverseChange">
                <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
              </select>
            </div>
            <div class="form-group" v-if="editForm.mode === 'proportional'">
              <label class="form-label">Base Value</label>
              <input type="number" class="form-input" v-model.number="bulkAdd.base_value" min="0" max="255">
            </div>
          </div>

          <div class="bulk-add-actions">
            <button class="btn btn-small btn-secondary" @click="selectAllChannels">Select All</button>
            <button class="btn btn-small btn-secondary" @click="clearSelection">Clear</button>
            <span class="selection-count">{{ selectedChannels.size }} selected</span>
          </div>
        </div>

        <div class="channel-grid-container">
          <div class="channel-grid">
            <div
              v-for="ch in 512"
              :key="ch"
              class="channel-tile"
              :class="{
                selected: selectedChannels.has(ch),
                'in-group': isChannelInGroup(bulkAdd.universe_id, ch)
              }"
              :style="getChannelTileStyle(ch)"
              @click="toggleChannel(ch, $event)"
              @mousedown="startChannelDrag(ch)"
              @mouseenter="dragSelectChannel(ch)"
            >
              <span class="channel-number">{{ ch }}</span>
              <div v-if="getChannelGroupColor(ch)"
                class="tile-group-stripe"
                :class="{
                  'connects-left': hasSameGroupColorLeft(ch),
                  'connects-right': hasSameGroupColorRight(ch)
                }"
                :style="{ backgroundColor: getChannelGroupColor(ch) }">
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="closeBulkAddModal">Cancel</button>
          <button
            type="button"
            class="btn btn-primary"
            @click="addBulkMembers"
            :disabled="selectedChannels.size === 0"
          >
            Add {{ selectedChannels.size }} Channels
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, reactive, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useDmxStore } from '../stores/dmx.js'
import { useAuthStore } from '../stores/auth.js'
import { wsManager } from '../websocket.js'

const dmxStore = useDmxStore()
const authStore = useAuthStore()
const { universes } = storeToRefs(dmxStore)

const groups = ref([])
const groupValues = reactive({})  // { group_id: value }
const showAddGroup = ref(false)
const showBulkAdd = ref(false)
const editMode = ref(false)
const selectedGroup = ref(null)
const deletingGroup = ref(null)
const dragging = ref(null)
const selectedChannels = ref(new Set())
const lastClickedChannel = ref(null)
const isDraggingChannels = ref(false)
const dragMode = ref(null)  // 'select' or 'deselect'

// Form for creating new groups
const groupForm = ref({
  name: '',
  mode: 'proportional',
  enabled: true
})

// Form for editing selected group
const editForm = ref({
  name: '',
  mode: 'proportional',
  enabled: true,
  master_universe: null,
  master_channel: null,
  color: null
})

// New member form
const newMember = ref({
  universe_id: 1,
  channel: 1,
  base_value: 255
})

// Inline member editing
const editingMember = ref(null)  // member.id being edited
const editMemberValue = ref(255) // temp value during edit

// Bulk base value editing
const showBulkBaseEdit = ref(false)
const bulkBaseValue = ref(255)

// Bulk add form
const bulkAdd = ref({
  universe_id: 1,
  base_value: 255
})

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

const canCreateGroup = computed(() => {
  return groupForm.value.name.trim() !== ''
})

const canAddMember = computed(() => {
  return newMember.value.universe_id && newMember.value.channel >= 1 && newMember.value.channel <= 512
})

onMounted(async () => {
  await dmxStore.loadUniverses()
  await loadGroups()
  if (universes.value.length > 0) {
    newMember.value.universe_id = universes.value[0].id
  }

  // Listen for group value changes from other clients
  wsManager.on('group_value_changed', handleGroupValueChanged)

  // Listen for group list changes (create/update/delete) from other clients
  wsManager.on('groups_changed', handleGroupsChanged)

  // Setup drag event listeners
  document.addEventListener('mousemove', handleDrag)
  document.addEventListener('mouseup', stopDrag)
  document.addEventListener('mouseup', stopChannelDrag)
  document.addEventListener('touchmove', handleDrag)
  document.addEventListener('touchend', stopDrag)
})

function stopChannelDrag() {
  isDraggingChannels.value = false
}

onUnmounted(() => {
  wsManager.off('group_value_changed', handleGroupValueChanged)
  wsManager.off('groups_changed', handleGroupsChanged)
  document.removeEventListener('mousemove', handleDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', handleDrag)
  document.removeEventListener('touchend', stopDrag)
})

function handleGroupValueChanged(data) {
  groupValues[data.group_id] = data.value
}

async function handleGroupsChanged() {
  // Reload groups list when another client makes changes
  await loadGroups()
  // Update selected group reference if it still exists
  if (selectedGroup.value) {
    selectedGroup.value = groups.value.find(g => g.id === selectedGroup.value.id) || null
    if (selectedGroup.value) {
      // Update edit form with new data
      editForm.value = {
        name: selectedGroup.value.name,
        mode: selectedGroup.value.mode,
        enabled: selectedGroup.value.enabled,
        master_universe: selectedGroup.value.master_universe,
        master_channel: selectedGroup.value.master_channel,
        color: selectedGroup.value.color
      }
    }
  }
}

async function loadGroups() {
  try {
    const response = await fetchWithAuth('/api/groups')
    const data = await response.json()
    groups.value = data.groups || []

    // Initialize group values from stored master_value
    for (const group of groups.value) {
      groupValues[group.id] = group.master_value || 0
    }
  } catch (e) {
    console.error('Failed to load groups:', e)
  }
}

async function selectGroup(group) {
  selectedGroup.value = group
  editForm.value = {
    name: group.name,
    mode: group.mode,
    enabled: group.enabled,
    master_universe: group.master_universe,
    master_channel: group.master_channel,
    color: group.color
  }
  // Load channel labels for all universes in this group's members
  const universeIds = new Set(group.members?.map(m => m.universe_id) || [])
  for (const uid of universeIds) {
    await dmxStore.loadChannelLabels(uid)
  }
}

function openNewGroupModal() {
  groupForm.value = {
    name: '',
    mode: 'proportional',
    enabled: true
  }
  showAddGroup.value = true
}

function closeGroupModal() {
  showAddGroup.value = false
}

async function createGroup() {
  try {
    const response = await fetchWithAuth('/api/groups', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: groupForm.value.name,
        mode: groupForm.value.mode,
        enabled: groupForm.value.enabled
      })
    })

    if (response.ok) {
      closeGroupModal()
      await loadGroups()
    } else {
      const error = await response.json()
      console.error('Failed to create group:', response.status, error)
      alert('Failed to create group: ' + (error.detail || 'Unknown error'))
    }
  } catch (e) {
    console.error('Failed to create group:', e)
    alert('Failed to create group: ' + e.message)
  }
}

async function saveGroupChanges() {
  if (!selectedGroup.value) return

  try {
    await fetchWithAuth(`/api/groups/${selectedGroup.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: editForm.value.name,
        mode: editForm.value.mode,
        enabled: editForm.value.enabled,
        master_universe: editForm.value.master_universe || null,
        master_channel: editForm.value.master_channel || null,
        color: editForm.value.color || null
      })
    })
    await loadGroups()
    // Update selected group reference
    selectedGroup.value = groups.value.find(g => g.id === selectedGroup.value.id)
  } catch (e) {
    console.error('Failed to save group:', e)
  }
}

function confirmDeleteGroup() {
  deletingGroup.value = selectedGroup.value
}

async function deleteGroup() {
  try {
    await fetchWithAuth(`/api/groups/${deletingGroup.value.id}`, {
      method: 'DELETE'
    })
    deletingGroup.value = null
    selectedGroup.value = null
    await loadGroups()
  } catch (e) {
    console.error('Failed to delete group:', e)
  }
}

async function addMember() {
  if (!selectedGroup.value || !canAddMember.value) return

  try {
    await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        universe_id: newMember.value.universe_id,
        channel: newMember.value.channel,
        base_value: newMember.value.base_value
      })
    })
    await loadGroups()
    selectedGroup.value = groups.value.find(g => g.id === selectedGroup.value.id)
    newMember.value.channel++
  } catch (e) {
    console.error('Failed to add member:', e)
  }
}

async function removeMember(member) {
  if (!selectedGroup.value) return

  try {
    await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members/${member.id}`, {
      method: 'DELETE'
    })
    await loadGroups()
    selectedGroup.value = groups.value.find(g => g.id === selectedGroup.value.id)
  } catch (e) {
    console.error('Failed to remove member:', e)
  }
}

// Inline member editing
function startMemberEdit(member) {
  editingMember.value = member.id
  editMemberValue.value = member.base_value
  nextTick(() => {
    const input = document.querySelector('.member-base-input')
    if (input) input.focus()
  })
}

function cancelMemberEdit() {
  editingMember.value = null
}

async function saveMemberEdit(member) {
  if (editingMember.value !== member.id) return

  const newValue = Math.max(0, Math.min(255, editMemberValue.value))
  if (newValue === member.base_value) {
    editingMember.value = null
    return
  }

  try {
    await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members/${member.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        universe_id: member.universe_id,
        channel: member.channel,
        base_value: newValue
      })
    })
    await loadGroups()
    selectedGroup.value = groups.value.find(g => g.id === selectedGroup.value.id)
  } catch (e) {
    console.error('Failed to update member:', e)
  }
  editingMember.value = null
}

// Bulk base value editing
async function applyBulkBaseValue() {
  if (!selectedGroup.value?.members?.length) return

  const value = Math.max(0, Math.min(255, bulkBaseValue.value))

  try {
    for (const member of selectedGroup.value.members) {
      await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members/${member.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          universe_id: member.universe_id,
          channel: member.channel,
          base_value: value
        })
      })
    }
    await loadGroups()
    selectedGroup.value = groups.value.find(g => g.id === selectedGroup.value.id)
  } catch (e) {
    console.error('Failed to bulk update members:', e)
  }
  showBulkBaseEdit.value = false
}

// Get member label from channel labels (fixture name + fader label)
function getMemberLabel(member) {
  const label = dmxStore.getChannelLabel(member.universe_id, member.channel)
  if (label && label !== `Ch ${member.channel}`) {
    // Truncate if too long
    return label.length > 20 ? label.substring(0, 18) + '...' : label
  }
  return null
}

// Bulk add functions
async function openBulkAddModal() {
  if (!selectedGroup.value) return
  bulkAdd.value.universe_id = universes.value[0]?.id || 1
  bulkAdd.value.base_value = 255
  selectedChannels.value = new Set()
  lastClickedChannel.value = null
  showBulkAdd.value = true
  // Load channel labels for the selected universe (for colors and group stripes)
  await dmxStore.loadChannelLabels(bulkAdd.value.universe_id)
}

async function onBulkUniverseChange() {
  selectedChannels.value = new Set()  // Clear selection when universe changes
  await dmxStore.loadChannelLabels(bulkAdd.value.universe_id)
}

function closeBulkAddModal() {
  showBulkAdd.value = false
  selectedChannels.value = new Set()
  isDraggingChannels.value = false
}

function isChannelInGroup(universeId, channel) {
  if (!selectedGroup.value?.members) return false
  return selectedGroup.value.members.some(
    m => m.universe_id === universeId && m.channel === channel
  )
}

// Channel color and group stripe helpers for bulk add modal
function getChannelTileStyle(channel) {
  // Don't apply custom background if selected (let .selected class handle it)
  if (selectedChannels.value.has(channel)) return {}

  const color = dmxStore.getChannelColor(bulkAdd.value.universe_id, channel)
  if (color && color !== 'var(--accent)') {
    // Return a dimmed version of the channel color (25% opacity)
    return { backgroundColor: color + '40' }
  }
  return {}
}

function getChannelGroupColor(channel) {
  return dmxStore.getChannelGroupColor(bulkAdd.value.universe_id, channel)
}

function hasSameGroupColorLeft(channel) {
  if (channel <= 1) return false
  const current = getChannelGroupColor(channel)
  const left = getChannelGroupColor(channel - 1)
  return current && left && current === left
}

function hasSameGroupColorRight(channel) {
  if (channel >= 512) return false
  const current = getChannelGroupColor(channel)
  const right = getChannelGroupColor(channel + 1)
  return current && right && current === right
}

function toggleChannel(ch, event) {
  // Skip if channel is already in group
  if (isChannelInGroup(bulkAdd.value.universe_id, ch)) return

  const newSet = new Set(selectedChannels.value)

  // Shift+click for range selection
  if (event.shiftKey && lastClickedChannel.value !== null) {
    const start = Math.min(lastClickedChannel.value, ch)
    const end = Math.max(lastClickedChannel.value, ch)
    for (let i = start; i <= end; i++) {
      if (!isChannelInGroup(bulkAdd.value.universe_id, i)) {
        newSet.add(i)
      }
    }
  } else {
    // Toggle single channel
    if (newSet.has(ch)) {
      newSet.delete(ch)
    } else {
      newSet.add(ch)
    }
  }

  selectedChannels.value = newSet
  lastClickedChannel.value = ch
}

function startChannelDrag(ch) {
  if (isChannelInGroup(bulkAdd.value.universe_id, ch)) return
  isDraggingChannels.value = true
  // Determine if we're selecting or deselecting based on current state
  dragMode.value = selectedChannels.value.has(ch) ? 'deselect' : 'select'
}

function dragSelectChannel(ch) {
  if (!isDraggingChannels.value) return
  if (isChannelInGroup(bulkAdd.value.universe_id, ch)) return

  const newSet = new Set(selectedChannels.value)
  if (dragMode.value === 'select') {
    newSet.add(ch)
  } else {
    newSet.delete(ch)
  }
  selectedChannels.value = newSet
}

function selectAllChannels() {
  const newSet = new Set()
  for (let i = 1; i <= 512; i++) {
    if (!isChannelInGroup(bulkAdd.value.universe_id, i)) {
      newSet.add(i)
    }
  }
  selectedChannels.value = newSet
}

function clearSelection() {
  selectedChannels.value = new Set()
}

async function addBulkMembers() {
  if (!selectedGroup.value || selectedChannels.value.size === 0) return

  const members = Array.from(selectedChannels.value).map(ch => ({
    universe_id: bulkAdd.value.universe_id,
    channel: ch,
    base_value: bulkAdd.value.base_value
  }))

  try {
    const response = await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members/bulk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ members })
    })

    if (response.ok) {
      const result = await response.json()
      closeBulkAddModal()
      await loadGroups()
      selectedGroup.value = groups.value.find(g => g.id === selectedGroup.value.id)
    } else {
      const error = await response.json()
      alert('Failed to add members: ' + (error.detail || 'Unknown error'))
    }
  } catch (e) {
    console.error('Failed to add bulk members:', e)
    alert('Failed to add members: ' + e.message)
  }
}

// Fader drag handling
function startDrag(event, group) {
  if (!group.enabled) return
  event.preventDefault()
  dragging.value = { group, element: event.target.closest('.fader-track') }
  handleDrag(event)
}

function handleDrag(event) {
  if (!dragging.value) return
  event.preventDefault()

  const { group, element } = dragging.value
  const rect = element.getBoundingClientRect()
  const clientY = event.touches ? event.touches[0].clientY : event.clientY
  const y = rect.bottom - clientY
  const height = rect.height
  const value = Math.round(Math.max(0, Math.min(255, (y / height) * 255)))

  // Update local value immediately for responsive UI
  groupValues[group.id] = value

  // Debounce API calls
  triggerGroup(group.id, value)
}

function stopDrag() {
  dragging.value = null
}

// Debounced trigger
let triggerTimeout = null
let activeSceneClearTimeout = null  // Debounce active scene clear to avoid flooding WebSocket

function triggerGroup(groupId, value) {
  // Clear active scene since user manually changed group fader (debounced to avoid flooding)
  if (!dmxStore.sceneRecallInProgress && !activeSceneClearTimeout) {
    wsManager.setActiveScene(null)
    activeSceneClearTimeout = setTimeout(() => {
      activeSceneClearTimeout = null
    }, 100)  // Only send once per 100ms
  }

  if (triggerTimeout) clearTimeout(triggerTimeout)
  triggerTimeout = setTimeout(async () => {
    try {
      await fetchWithAuth(`/api/groups/${groupId}/trigger?value=${value}`, {
        method: 'POST'
      })
    } catch (e) {
      console.error('Failed to trigger group:', e)
    }
  }, 30)  // 30ms debounce
}
</script>

<style scoped>
.groups-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.header-actions {
  display: flex;
  gap: 16px;
  align-items: center;
}

.edit-mode-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 14px;
  color: var(--text-secondary);
}

.edit-mode-toggle input {
  accent-color: var(--accent);
}

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

.groups-layout {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.groups-grid-container {
  flex: 1;
  overflow: auto;
}

.groups-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding: 16px;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border);
}

.group-fader {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 8px;
  background: var(--bg-tertiary);
  border: 2px solid var(--border);
  border-radius: 8px;
  min-width: 70px;
  cursor: pointer;
  transition: all 0.15s;
  position: relative;
}

.group-fader:hover {
  border-color: var(--text-secondary);
}

.group-fader.selected {
  border-color: var(--accent);
  box-shadow: 0 0 8px rgba(233, 69, 96, 0.3);
}

.group-fader.disabled {
  opacity: 0.5;
}

.group-fader.disabled .fader-track {
  cursor: not-allowed;
}

.group-name {
  font-size: 11px;
  font-weight: 600;
  text-align: center;
  max-width: 60px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fader-track {
  width: 30px;
  height: 120px;
  background: var(--bg-primary);
  border-radius: 4px;
  position: relative;
  cursor: pointer;
  border: 1px solid var(--border);
  overflow: hidden;
}

.fader-fill {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--accent);
  transition: height 0.05s;
  border-radius: 0 0 3px 3px;
}

.group-value {
  font-size: 12px;
  font-weight: bold;
  color: var(--text-primary);
}

.badge-row {
  display: flex;
  gap: 4px;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
}

.mode-badge {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 600;
}

.mode-badge.proportional {
  background: rgba(59, 130, 246, 0.2);
  color: #60a5fa;
}

.mode-badge.follow {
  background: rgba(168, 85, 247, 0.2);
  color: #c084fc;
}

/* Edit Panel */
.edit-panel {
  width: 300px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 200px);
}

.edit-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.edit-panel-header h3 {
  margin: 0;
  font-size: 16px;
}

.edit-panel-content {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.checkbox-label input {
  accent-color: var(--accent);
}

/* DMX Input Link section */
.input-link-section {
  margin-top: 20px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border);
}

.input-link-section h4 {
  margin: 0 0 8px 0;
  font-size: 13px;
  color: var(--text-primary);
}

.help-text {
  font-size: 11px;
  color: var(--text-secondary);
  margin: 0 0 12px 0;
  line-height: 1.4;
}

.input-link-row {
  display: flex;
  gap: 8px;
}

.input-link-row .form-group {
  flex: 1;
  margin-bottom: 0;
}

.input-link-row .form-select,
.input-link-row .form-input {
  font-size: 12px;
  padding: 6px 8px;
}

.members-section {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.members-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.members-header h4 {
  margin: 0;
  font-size: 14px;
}

.members-header-buttons {
  display: flex;
  gap: 4px;
}

.bulk-base-edit {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  margin-bottom: 8px;
}

.bulk-base-edit label {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.bulk-base-edit .form-input {
  width: 60px;
}

.add-member-row {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}

.add-member-row .form-select,
.add-member-row .form-input {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  padding: 6px 8px;
}

.add-member-row .form-input {
  width: 50px;
}

.members-list {
  max-height: 200px;
  overflow-y: auto;
}

.member-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  margin-bottom: 4px;
}

.member-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.member-channel {
  font-size: 11px;
  font-family: monospace;
  color: var(--text-secondary);
}

.member-label {
  font-size: 12px;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.member-base {
  font-size: 11px;
  color: var(--text-secondary);
}

.member-base.editable {
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
}

.member-base.editable:hover {
  background: var(--bg-secondary);
}

.member-base-input {
  width: 50px;
  padding: 2px 4px;
  font-size: 12px;
}

.no-members {
  text-align: center;
  color: var(--text-secondary);
  font-size: 12px;
  padding: 12px;
}

.danger-zone {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

/* Modal styles */
.modal-standard {
  width: 400px;
  max-width: 90vw;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}

/* Bulk Add Modal */
.modal-bulk-add {
  width: 90vw;
  max-width: 900px;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.bulk-add-controls {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.bulk-add-row {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
}

.bulk-add-row .form-group {
  margin-bottom: 0;
}

.bulk-add-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.selection-count {
  margin-left: auto;
  font-size: 13px;
  color: var(--text-secondary);
}

.channel-grid-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-height: 300px;
  max-height: 50vh;
}

.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(42px, 1fr));
  gap: 4px;
  user-select: none;
}

.channel-tile {
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  border: 2px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.1s;
  font-size: 11px;
  font-weight: 500;
  position: relative;
}

.channel-tile:hover {
  border-color: var(--text-secondary);
  background: var(--bg-secondary);
}

.channel-tile.selected {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.channel-tile.in-group {
  background: var(--bg-primary);
  border-color: var(--border);
  color: var(--text-secondary);
  opacity: 0.5;
  cursor: not-allowed;
}

.channel-number {
  pointer-events: none;
}

/* Tile group stripe (like on /faders) */
.tile-group-stripe {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3px;
  border-radius: 0 0 2px 2px;
  pointer-events: none;
}

.tile-group-stripe.connects-left {
  left: -2px;
  border-bottom-left-radius: 0;
}

.tile-group-stripe.connects-right {
  right: -2px;
  border-bottom-right-radius: 0;
}

/* DMX Input badge on group faders */
.dmx-input-badge {
  font-size: 9px;
  color: var(--indicator-remote);
  background: rgba(0, 188, 212, 0.15);
  padding: 2px 6px;
  border-radius: 4px;
}

/* Color picker in edit panel */
.color-input-wrapper {
  display: flex;
  gap: 8px;
  align-items: center;
}

.color-input-wrapper input[type="color"] {
  width: 36px;
  height: 28px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  padding: 0;
  background: transparent;
}

.color-input-wrapper input[type="color"]::-webkit-color-swatch-wrapper {
  padding: 0;
}

.color-input-wrapper input[type="color"]::-webkit-color-swatch {
  border: 1px solid var(--border);
  border-radius: 4px;
}

.color-hex {
  width: 80px;
  font-family: monospace;
  font-size: 12px;
}

/* Responsive */
@media (max-width: 768px) {
  .groups-layout {
    flex-direction: column;
  }

  .edit-panel {
    width: 100%;
    max-height: none;
  }

  .group-fader {
    min-width: 60px;
  }

  .fader-track {
    height: 100px;
  }

  .modal-bulk-add {
    width: 95vw;
  }

  .channel-grid {
    grid-template-columns: repeat(auto-fill, minmax(36px, 1fr));
  }
}
</style>

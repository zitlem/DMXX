<template>
  <div class="groups-page" :class="{ 'edit-mode-active': editMode, 'single-grid-view': singleGridMode }">
    <!-- Single Grid Header (when viewing ?grid=X) -->
    <div v-if="singleGridMode" class="single-grid-header">
      <button class="btn btn-secondary" @click="exitSingleGridMode">
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        All Grids
      </button>
      <h2 class="card-title">{{ currentGrid?.name || 'Grid' }}</h2>
      <div class="header-actions-row">
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
        <div class="header-actions" v-if="authStore.isAdmin">
          <label class="edit-mode-toggle">
            <input type="checkbox" v-model="editMode">
            <span>Edit Mode</span>
          </label>
          <button class="btn btn-primary" @click="openNewGroupModal">+ Add Group</button>
        </div>
      </div>
    </div>

    <!-- Regular Header (all grids view) -->
    <div v-else class="card-header">
      <h2 class="card-title">Groups / Masters</h2>
      <div class="header-actions-row">
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
        <div class="header-actions" v-if="authStore.isAdmin">
          <label class="edit-mode-toggle">
            <input type="checkbox" v-model="editMode">
            <span>Edit Mode</span>
          </label>
          <button class="btn btn-secondary" @click="openNewGridModal">+ Add Grid</button>
          <button class="btn btn-primary" @click="openNewGroupModal">+ Add Group</button>
        </div>
      </div>
    </div>

    <!-- Info Note -->
    <div class="info-banner" v-if="grids.length === 0 || (grids.length === 1 && getAllGroups.length === 0)">
      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <span>No groups created yet. <strong v-if="authStore.isAdmin">Click "+ Add Group" to create your first group.</strong></span>
    </div>

    <!-- Main Layout -->
    <div class="groups-layout">
      <!-- Grids Container -->
      <draggable
        v-model="displayedGrids"
        class="grids-container"
        :disabled="!editMode || singleGridMode"
        item-key="id"
        :animation="200"
        ghost-class="grid-ghost"
        drag-class="grid-dragging"
        handle=".grid-drag-handle"
        @end="onGridDragEnd"
      >
        <template #item="{ element: grid }">
          <div
            class="group-grid"
            :class="{ 'single-mode': singleGridMode }"
          >
            <!-- Vertical Title Bar -->
            <div
              class="grid-title-bar"
              :style="{ background: grid.color || 'var(--accent)' }"
              @click="handleTitleBarClick(grid)"
            >
              <div class="grid-title-content">
                <span class="grid-title">{{ grid.name }}</span>
                <div v-if="editMode" class="grid-edit-indicator">
                  <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </div>
                <div v-if="editMode && !singleGridMode" class="grid-drag-handle">
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                    <circle cx="9" cy="6" r="2"/><circle cx="15" cy="6" r="2"/>
                    <circle cx="9" cy="12" r="2"/><circle cx="15" cy="12" r="2"/>
                    <circle cx="9" cy="18" r="2"/><circle cx="15" cy="18" r="2"/>
                  </svg>
                </div>
              </div>
            </div>

          <!-- Groups Grid Area -->
          <div class="groups-grid-container">
            <draggable
              v-model="grid.groups"
              class="groups-grid"
              :disabled="!editMode"
              item-key="id"
              :animation="200"
              ghost-class="group-fader-ghost"
              drag-class="group-fader-dragging"
              handle=".group-drag-handle"
              :delay="150"
              :delay-on-touch-only="true"
              :touch-start-threshold="5"
              filter=".fader-track"
              :prevent-on-filter="false"
              group="groups"
              @end="(e) => onDragEnd(e, grid)"
            >
              <template #item="{ element: group }">
                <div
                  class="group-fader"
                  :class="{
                    selected: editMode && selectedGroup?.id === group.id,
                    disabled: !group.enabled,
                    draggable: editMode
                  }"
                  @click="editMode && selectGroup(group)"
                >
                  <div v-if="editMode" class="group-drag-handle">
                    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <circle cx="9" cy="6" r="2"/><circle cx="15" cy="6" r="2"/>
                      <circle cx="9" cy="12" r="2"/><circle cx="15" cy="12" r="2"/>
                      <circle cx="9" cy="18" r="2"/><circle cx="15" cy="18" r="2"/>
                    </svg>
                  </div>
                  <span class="group-name" :title="group.name">{{ group.name }}</span>
                  <!-- Color Mixer Mode: Fader with long-press for color picker -->
                  <template v-if="group.mode === 'color_mixer'">
                    <div
                      class="color-mixer-fader"
                      :style="{
                        borderColor: getGroupColorPreview(group.id),
                        '--fill-height': (getGroupDisplayValue(group.id) / 255 * 100) + '%'
                      }"
                      @mousedown="startColorMixerDrag($event, group)"
                      @touchstart="startColorMixerDrag($event, group)"
                      title="Drag to adjust brightness, hold to open color picker"
                    >
                      <div
                        class="color-mixer-fill"
                        :style="{ background: getGroupColorPreview(group.id) }"
                      ></div>
                    </div>
                  </template>
                  <!-- Regular Fader Mode -->
                  <template v-else>
                    <div
                      class="fader-track"
                      @mousedown="startDrag($event, group)"
                      @touchstart="startDrag($event, group)"
                    >
                      <div
                        class="fader-fill"
                        :style="{ height: getGroupDisplayValue(group.id) / 255 * 100 + '%', background: group.color || 'var(--accent)' }"
                      ></div>
                    </div>
                  </template>
                  <div class="group-controls-row">
                    <button
                      v-if="authStore.canPark"
                      class="park-btn"
                      :class="{ active: isGroupParked(group.id) }"
                      @mousedown="startGroupParkPress(group)"
                      @mouseup="endGroupParkPress(group)"
                      @mouseleave="cancelGroupParkPress(group)"
                      @touchstart.prevent="startGroupParkPress(group)"
                      @touchend.prevent="endGroupParkPress(group)"
                      @touchcancel="cancelGroupParkPress(group)"
                      title="Long-press to park all group channels"
                    >P</button>
                    <span class="group-value">{{ Math.round(getGroupDisplayValue(group.id) / 255 * 100) }}%</span>
                    <button
                      v-if="authStore.canHighlight"
                      class="highlight-btn"
                      :class="{ active: isGroupHighlighted(group.id) }"
                      @mousedown="startGroupHighlightPress(group)"
                      @mouseup="endGroupHighlightPress(group)"
                      @mouseleave="cancelGroupHighlightPress(group)"
                      @touchstart.prevent="startGroupHighlightPress(group)"
                      @touchend.prevent="endGroupHighlightPress(group)"
                      @touchcancel="cancelGroupHighlightPress(group)"
                      title="Long-press to highlight all group channels"
                    >H</button>
                  </div>
                  <div class="badge-row">
                    <span class="mode-badge" :class="group.mode">{{ group.mode === 'proportional' ? 'P' : (group.mode === 'color_mixer' ? 'C' : 'F') }}</span>
                    <span v-if="group.master_channel" class="dmx-input-badge"
                      :title="`Controlled by Universe ${group.master_universe} Channel ${group.master_channel}`">
                      {{ group.master_universe }}.{{ group.master_channel }}
                    </span>
                  </div>
                </div>
              </template>
            </draggable>
            <div v-if="!grid.groups || grid.groups.length === 0" class="empty-grid-hint">
              <span>No groups in this grid</span>
            </div>
          </div>
        </div>
        </template>
      </draggable>

      <!-- Edit Panel (right sidebar, admin only) -->
      <div v-if="editMode && (selectedGroup || selectedGridForEdit)" class="edit-panel">
        <!-- Grid Edit Panel -->
        <template v-if="selectedGridForEdit && !selectedGroup">
          <div class="edit-panel-header">
            <h3>Edit Grid</h3>
            <button class="modal-close" @click="selectedGridForEdit = null">&times;</button>
          </div>

          <div class="edit-panel-content">
            <div class="form-group">
              <label class="form-label">Name</label>
              <input
                type="text"
                class="form-input"
                v-model="gridEditForm.name"
                @change="saveGridChanges"
              >
            </div>

            <div class="form-group">
              <label class="form-label">Title Bar Color</label>
              <div class="color-input-wrapper">
                <input
                  type="color"
                  :value="gridEditForm.color || '#e94560'"
                  @input="gridEditForm.color = $event.target.value; saveGridChanges()"
                >
                <input
                  type="text"
                  class="form-input color-hex"
                  :value="gridEditForm.color || ''"
                  @change="gridEditForm.color = $event.target.value || null; saveGridChanges()"
                  placeholder="Default"
                >
                <button
                  v-if="gridEditForm.color"
                  class="btn btn-small btn-secondary"
                  @click="gridEditForm.color = null; saveGridChanges()"
                  title="Reset to default"
                >Reset</button>
              </div>
            </div>

            <!-- Delete Grid Button -->
            <div class="danger-zone">
              <button class="btn btn-danger" @click="confirmDeleteGrid">Delete Grid</button>
              <p class="help-text">Groups will be moved to the first remaining grid.</p>
            </div>
          </div>
        </template>

        <!-- Group Edit Panel -->
        <template v-else-if="selectedGroup">
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
                <option value="color_mixer">Color Mixer</option>
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
                  <div class="input-link-channel-row">
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
                    <button
                      class="btn btn-small btn-secondary"
                      @click="openInputLinkPicker"
                      :disabled="!editForm.master_universe"
                      title="Pick channel from grid"
                    >Pick</button>
                  </div>
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
              <div class="add-member-row" :class="{ 'add-member-row--channel': newMember.target_type === 'channel' }">
                <select v-if="editForm.mode !== 'color_mixer'" class="form-select target-type-select" v-model="newMember.target_type">
                  <option value="channel">Channel</option>
                  <option value="universe_master">Universe Master</option>
                  <option value="global_master">Global Master</option>
                </select>
                <template v-if="newMember.target_type === 'channel' || editForm.mode === 'color_mixer'">
                  <select class="form-select" v-model.number="newMember.universe_id">
                    <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                  </select>
                  <input
                    type="text"
                    class="form-input channel-input"
                    v-model="newMember.channel"
                    placeholder="Ch (1,2,3)"
                    title="Separate multiple channels with commas"
                  >
                </template>
                <template v-else-if="newMember.target_type === 'universe_master'">
                  <select class="form-select" v-model.number="newMember.target_universe_id">
                    <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
                  </select>
                </template>
                <!-- global_master needs no additional inputs -->
                <span v-if="editForm.mode === 'proportional'" class="input-separator">@</span>
                <input
                  v-if="editForm.mode === 'proportional'"
                  type="number"
                  class="form-input"
                  v-model.number="newMember.base_value"
                  min="0"
                  max="255"
                  placeholder="Base"
                >
                <select
                  v-if="editForm.mode === 'color_mixer'"
                  class="form-select color-role-select"
                  v-model="newMember.color_role"
                >
                  <option value="">No Role</option>
                  <option value="red">Red</option>
                  <option value="green">Green</option>
                  <option value="blue">Blue</option>
                  <option value="white">White</option>
                  <option value="warm_white">Warm White</option>
                  <option value="cool_white">Cool White</option>
                  <option value="amber">Amber</option>
                  <option value="uv">UV</option>
                  <option value="lime">Lime</option>
                  <option value="cyan">Cyan</option>
                  <option value="magenta">Magenta</option>
                  <option value="yellow">Yellow</option>
                  <option value="orange">Orange</option>
                </select>
                <button class="btn btn-small btn-primary" @click="addMember" :disabled="!canAddMember">+</button>
              </div>

              <!-- Members List -->
              <div class="members-list">
                <div v-for="member in selectedGroup.members" :key="member.id" class="member-row">
                  <span class="member-info">
                    <template v-if="member.target_type === 'universe_master'">
                      <span class="member-channel master-target">U{{ member.target_universe_id }} Master</span>
                    </template>
                    <template v-else-if="member.target_type === 'global_master'">
                      <span class="member-channel master-target">Global Master</span>
                    </template>
                    <template v-else>
                      <span class="member-channel">U{{ member.universe_id }}.{{ member.channel }}</span>
                      <span v-if="getMemberLabel(member)" class="member-label" :title="dmxStore.getChannelLabel(member.universe_id, member.channel)">{{ getMemberLabel(member) }}</span>
                    </template>
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
                  <template v-if="editForm.mode === 'color_mixer'">
                    <select
                      class="form-select color-role-select"
                      :value="member.color_role || ''"
                      @change="updateMemberColorRole(member, $event.target.value)"
                    >
                      <option value="">No Role</option>
                      <option value="red">Red</option>
                      <option value="green">Green</option>
                      <option value="blue">Blue</option>
                      <option value="white">White</option>
                      <option value="warm_white">Warm White</option>
                      <option value="cool_white">Cool White</option>
                      <option value="amber">Amber</option>
                      <option value="uv">UV</option>
                      <option value="lime">Lime</option>
                      <option value="cyan">Cyan</option>
                      <option value="magenta">Magenta</option>
                      <option value="yellow">Yellow</option>
                      <option value="orange">Orange</option>
                    </select>
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
        </template>
      </div>
    </div>

    <!-- Add Grid Modal -->
    <div v-if="showAddGrid" class="modal-overlay">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">New Grid</h3>
          <button class="modal-close" @click="closeGridModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Grid Name</label>
          <input type="text" class="form-input" v-model="gridForm.name" placeholder="e.g., Stage Left">
        </div>

        <div class="form-group">
          <label class="form-label">Title Bar Color (optional)</label>
          <div class="color-input-wrapper">
            <input
              type="color"
              :value="gridForm.color || '#e94560'"
              @input="gridForm.color = $event.target.value"
            >
            <input
              type="text"
              class="form-input color-hex"
              v-model="gridForm.color"
              placeholder="Default"
            >
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="closeGridModal">Cancel</button>
          <button
            type="button"
            class="btn btn-primary"
            @click="createGrid"
            :disabled="!canCreateGrid"
          >
            Create Grid
          </button>
        </div>
      </div>
    </div>

    <!-- Add/Edit Group Modal -->
    <div v-if="showAddGroup" class="modal-overlay">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">New Group</h3>
          <button class="modal-close" @click="closeGroupModal">&times;</button>
        </div>

        <div class="form-group">
          <label class="form-label">Group Name(s)</label>
          <input type="text" class="form-input" v-model="groupForm.name" placeholder="e.g., Red Wash, Blue Wash, Amber">
          <span class="input-hint">Separate multiple names with commas</span>
        </div>

        <div class="form-group">
          <label class="form-label">Mode</label>
          <select class="form-select" v-model="groupForm.mode">
            <option value="proportional">Proportional (scales member base values)</option>
            <option value="follow">Follow (all members match master)</option>
            <option value="color_mixer">Color Mixer (RGB/RGBW color picker)</option>
          </select>
        </div>

        <!-- Grid Selection (only in all-grids view) -->
        <div class="form-group" v-if="!singleGridMode && grids.length > 1">
          <label class="form-label">Add to Grid</label>
          <select class="form-select" v-model.number="groupForm.grid_id">
            <option v-for="g in grids" :key="g.id" :value="g.id">{{ g.name }}</option>
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

    <!-- Delete Group Confirmation Modal -->
    <div v-if="deletingGroup" class="modal-overlay">
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

    <!-- Delete Grid Confirmation Modal -->
    <div v-if="deletingGrid" class="modal-overlay">
      <div class="modal modal-standard">
        <div class="modal-header">
          <h3 class="modal-title">Delete Grid</h3>
          <button class="modal-close" @click="deletingGrid = null">&times;</button>
        </div>
        <p>Are you sure you want to delete this grid?</p>
        <p style="color: var(--text-secondary);">{{ deletingGrid.name }}</p>
        <p class="help-text">Groups in this grid will be moved to the first remaining grid.</p>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="deletingGrid = null">Cancel</button>
          <button type="button" class="btn btn-danger" @click="deleteGrid">Delete</button>
        </div>
      </div>
    </div>

    <!-- Bulk Add Modal -->
    <div v-if="showBulkAdd" class="modal-overlay">
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

    <!-- Input Link Channel Picker Modal -->
    <div v-if="showInputLinkPicker" class="modal-overlay">
      <div class="modal modal-bulk-add">
        <div class="modal-header">
          <h3 class="modal-title">Select Input Channel</h3>
          <button class="modal-close" @click="closeInputLinkPicker">&times;</button>
        </div>

        <div class="bulk-add-controls">
          <div class="bulk-add-row">
            <div class="form-group">
              <label class="form-label">Universe</label>
              <select class="form-select" v-model.number="inputLinkPicker.universe_id">
                <option v-for="u in universes" :key="u.id" :value="u.id">{{ u.label }}</option>
              </select>
            </div>
          </div>
        </div>

        <div class="channel-grid-container">
          <div class="channel-grid">
            <div
              v-for="ch in 512"
              :key="ch"
              class="channel-tile"
              :class="{ selected: inputLinkPicker.channel === ch }"
              :style="getInputLinkTileStyle(ch)"
              @click="selectInputLinkChannel(ch)"
            >
              <span class="channel-number">{{ ch }}</span>
              <div v-if="getInputLinkGroupColor(ch)"
                class="tile-group-stripe"
                :class="{
                  'connects-left': hasInputLinkSameGroupColorLeft(ch),
                  'connects-right': hasInputLinkSameGroupColorRight(ch)
                }"
                :style="{ backgroundColor: getInputLinkGroupColor(ch) }">
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="closeInputLinkPicker">Cancel</button>
          <button
            type="button"
            class="btn btn-primary"
            @click="applyInputLinkChannel"
            :disabled="!inputLinkPicker.channel"
          >
            Set Channel {{ inputLinkPicker.channel || '' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Color Picker Modal -->
    <div v-if="colorPickerModal.visible" class="modal-overlay">
      <div class="modal modal-color-picker">
        <div class="modal-header">
          <h3 class="modal-title">Color Picker - {{ colorPickerModal.group?.name }}</h3>
          <button class="modal-close" @click="closeColorPickerModal">&times;</button>
        </div>

        <div class="color-picker-modal-content">
          <!-- Large color gradient -->
          <div
            class="color-picker-gradient-large"
            :style="{ background: `linear-gradient(to top, #000, transparent), linear-gradient(to right, #fff, hsl(${getGroupHue(colorPickerModal.group?.id)}, 100%, 50%))` }"
            @mousedown="startColorPickModal($event)"
            @touchstart="startColorPickModal($event)"
          >
            <div class="color-picker-cursor-large" :style="getColorCursorStyle(colorPickerModal.group?.id)"></div>
          </div>

          <!-- Hue slider -->
          <input
            type="range"
            class="hue-slider-large"
            min="0"
            max="360"
            :value="getGroupHue(colorPickerModal.group?.id)"
            @input="updateGroupHueModal($event.target.value)"
          >

          <!-- RGB Inputs -->
          <div class="rgb-inputs">
            <div class="rgb-input-group">
              <label>R</label>
              <input type="number" class="form-input" min="0" max="255" :value="colorPickerModal.rgb.r" @input="updateRgbValue('r', $event.target.value)">
            </div>
            <div class="rgb-input-group">
              <label>G</label>
              <input type="number" class="form-input" min="0" max="255" :value="colorPickerModal.rgb.g" @input="updateRgbValue('g', $event.target.value)">
            </div>
            <div class="rgb-input-group">
              <label>B</label>
              <input type="number" class="form-input" min="0" max="255" :value="colorPickerModal.rgb.b" @input="updateRgbValue('b', $event.target.value)">
            </div>
          </div>

          <!-- Brightness slider -->
          <div class="brightness-section">
            <label class="form-label">Brightness</label>
            <div class="brightness-slider-row">
              <input
                type="range"
                class="brightness-slider"
                min="0"
                max="255"
                :value="colorPickerModal.brightness"
                @input="updateBrightness($event.target.value)"
              >
              <span class="brightness-value">{{ colorPickerModal.brightness }}</span>
            </div>
          </div>

          <!-- Large color preview -->
          <div class="color-preview-large" :style="{ background: getGroupColorPreview(colorPickerModal.group?.id) }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, reactive, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import draggable from 'vuedraggable'
import { useDmxStore } from '../stores/dmx.js'
import { useAuthStore } from '../stores/auth.js'
import { wsManager } from '../websocket.js'

const route = useRoute()
const router = useRouter()
const dmxStore = useDmxStore()
const authStore = useAuthStore()
const { universes } = storeToRefs(dmxStore)

// Grid state
const grids = ref([])
const showAddGrid = ref(false)
const selectedGridForEdit = ref(null)
const deletingGrid = ref(null)

// Grid form for creating new grids
const gridForm = ref({
  name: '',
  color: null
})

// Grid edit form
const gridEditForm = ref({
  name: '',
  color: null
})

// URL parameter handling
const singleGridMode = computed(() => !!route.query.grid)
const currentGridId = computed(() => route.query.grid ? parseInt(route.query.grid) : null)
const currentGrid = computed(() => {
  if (!currentGridId.value) return null
  return grids.value.find(g => g.id === currentGridId.value)
})

// Grids filtered by user access (writable for draggable)
const accessibleGrids = computed({
  get() {
    return grids.value.filter(grid => authStore.hasGridAccess(grid.id))
  },
  set(newValue) {
    // Update the main grids array with new order
    const inaccessibleGrids = grids.value.filter(g => !authStore.hasGridAccess(g.id))
    grids.value = [...newValue, ...inaccessibleGrids]
  }
})

// Displayed grids (filtered by URL param and access, writable for draggable)
const displayedGrids = computed({
  get() {
    if (singleGridMode.value && currentGridId.value) {
      const grid = accessibleGrids.value.find(g => g.id === currentGridId.value)
      return grid ? [grid] : []
    }
    return accessibleGrids.value
  },
  set(newValue) {
    // Only allow reorder when not in single grid mode
    if (!singleGridMode.value) {
      accessibleGrids.value = newValue
    }
  }
})

// Get all groups across all grids (for info banner)
const getAllGroups = computed(() => {
  return grids.value.flatMap(g => g.groups || [])
})

// Check if any channels are parked
const hasParkedChannels = computed(() => {
  return Object.keys(dmxStore.parkedChannels).some(uid =>
    Object.keys(dmxStore.parkedChannels[uid] || {}).length > 0
  )
})

const groupValues = reactive({})  // { group_id: value }
const colorPickerState = reactive({})  // { group_id: { h: 0-360, s: 0-100, l: 0-100 } }
const colorPickingGroup = ref(null)  // group being color picked
const colorPickerModal = ref({
  visible: false,
  group: null,
  rgb: { r: 0, g: 0, b: 0 },
  brightness: 100
})
const colorMixerDragging = ref(null)  // { groupId: number, cancel: () => void } for external drag cancellation
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
  enabled: true,
  grid_id: null
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
  channel: '1',  // String to support comma-separated input (e.g., "1,2,3")
  base_value: 255,
  target_type: 'channel',  // 'channel', 'universe_master', 'global_master'
  target_universe_id: 1,
  color_role: ''  // For color_mixer mode
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

// Input link channel picker state
const showInputLinkPicker = ref(false)
const inputLinkPicker = ref({
  universe_id: 1,
  channel: null
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

const canCreateGrid = computed(() => {
  return gridForm.value.name.trim() !== ''
})

const canAddMember = computed(() => {
  const targetType = newMember.value.target_type
  if (targetType === 'channel') {
    if (!newMember.value.universe_id) return false
    // Support comma-separated channels (e.g., "1,2,3")
    const channelStr = String(newMember.value.channel || '')
    const channels = channelStr.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n))
    return channels.length > 0 && channels.every(ch => ch >= 1 && ch <= 512)
  } else if (targetType === 'universe_master') {
    return newMember.value.target_universe_id
  } else if (targetType === 'global_master') {
    return true  // Global master needs no additional params
  }
  return false
})

onMounted(async () => {
  await dmxStore.loadUniverses()
  await loadGrids()
  dmxStore.checkInputBypassStatus()
  dmxStore.loadAllParkedChannels()
  dmxStore.loadHighlightState()
  if (universes.value.length > 0) {
    newMember.value.universe_id = universes.value[0].id
  }

  // Listen for group value changes from other clients
  wsManager.on('group_value_changed', handleGroupValueChanged)

  // Listen for group list changes (create/update/delete) from other clients
  wsManager.on('groups_changed', handleGroupsChanged)

  // Listen for grid changes
  wsManager.on('grids_changed', handleGridsChanged)

  // Listen for universe values to initialize color mixer states
  wsManager.on('all_values', initAllColorMixerStates)

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
  wsManager.off('grids_changed', handleGridsChanged)
  wsManager.off('all_values', initAllColorMixerStates)
  document.removeEventListener('mousemove', handleDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', handleDrag)
  document.removeEventListener('touchend', stopDrag)
})

async function toggleBypass() {
  try {
    await dmxStore.toggleInputBypass()
  } catch (e) {
    console.error('Failed to toggle bypass:', e)
  }
}

function handleGroupValueChanged(data) {
  groupValues[data.group_id] = data.value

  // If change came from IO input, cancel any active drag for this group
  // This allows the fader to "snap back" to the input-controlled value
  if (data.source === 'input') {
    // Cancel color mixer drag
    if (colorMixerDragging.value?.groupId === data.group_id) {
      colorMixerDragging.value.cancel()
    }
    // Cancel regular fader drag
    if (dragging.value?.group?.id === data.group_id) {
      dragging.value = null
    }
  }

  // Sync modal brightness if this group's modal is open
  if (colorPickerModal.value.visible && colorPickerModal.value.group?.id === data.group_id) {
    colorPickerModal.value.brightness = data.value
  }

  // For color_mixer groups, update local state for UI display only
  // Backend handles the actual color calculation and channel output
  const allGroups = grids.value.flatMap(g => g.groups || [])
  const group = allGroups.find(g => g.id === data.group_id)
  if (group && group.mode === 'color_mixer') {
    // Only initialize local color state for UI display if needed
    if (!colorPickerState[data.group_id]) {
      initColorPickerStateFromChannels(group)
    }
    // DON'T call applyColorToGroup() - backend handles output
  }
}

async function handleGroupsChanged() {
  // Reload grids (which include groups) when another client makes changes
  await loadGrids()
  // Update selected group reference if it still exists
  if (selectedGroup.value) {
    const allGroups = grids.value.flatMap(g => g.groups || [])
    selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id) || null
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

async function handleGridsChanged() {
  await loadGrids()
  // Update selected grid reference if it still exists
  if (selectedGridForEdit.value) {
    selectedGridForEdit.value = grids.value.find(g => g.id === selectedGridForEdit.value.id) || null
    if (selectedGridForEdit.value) {
      gridEditForm.value = {
        name: selectedGridForEdit.value.name,
        color: selectedGridForEdit.value.color
      }
    }
  }
}

// Grid navigation
function openGrid(gridId) {
  router.push({ path: '/groups', query: { grid: gridId } })
}

function exitSingleGridMode() {
  router.push({ path: '/groups' })
}

function handleTitleBarClick(grid) {
  // In edit mode: always select grid for editing (don't navigate)
  if (editMode.value) {
    selectGrid(grid)
    return
  }

  // Not in edit mode: navigate
  if (singleGridMode.value) {
    exitSingleGridMode()
  } else {
    openGrid(grid.id)
  }
}

// Grid CRUD
function openNewGridModal() {
  gridForm.value = {
    name: '',
    color: null
  }
  showAddGrid.value = true
}

function closeGridModal() {
  showAddGrid.value = false
}

async function createGrid() {
  try {
    const response = await fetchWithAuth('/api/groups/grids', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: gridForm.value.name,
        color: gridForm.value.color || null
      })
    })

    if (response.ok) {
      closeGridModal()
      await loadGrids()
    } else {
      const error = await response.json()
      console.error('Failed to create grid:', response.status, error)
      alert('Failed to create grid: ' + (error.detail || 'Unknown error'))
    }
  } catch (e) {
    console.error('Failed to create grid:', e)
    alert('Failed to create grid: ' + e.message)
  }
}

function selectGrid(grid) {
  selectedGroup.value = null  // Deselect group when selecting grid
  selectedGridForEdit.value = grid
  gridEditForm.value = {
    name: grid.name,
    color: grid.color
  }
}

async function saveGridChanges() {
  if (!selectedGridForEdit.value) return

  try {
    await fetchWithAuth(`/api/groups/grids/${selectedGridForEdit.value.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: gridEditForm.value.name,
        color: gridEditForm.value.color || null
      })
    })
    await loadGrids()
    // Update selected grid reference
    selectedGridForEdit.value = grids.value.find(g => g.id === selectedGridForEdit.value.id)
  } catch (e) {
    console.error('Failed to save grid:', e)
  }
}

function confirmDeleteGrid() {
  deletingGrid.value = selectedGridForEdit.value
}

async function deleteGrid() {
  try {
    await fetchWithAuth(`/api/groups/grids/${deletingGrid.value.id}`, {
      method: 'DELETE'
    })
    deletingGrid.value = null
    selectedGridForEdit.value = null
    await loadGrids()
  } catch (e) {
    console.error('Failed to delete grid:', e)
  }
}

async function onDragEnd(event, sourceGrid) {
  const movedGroup = event.item?.__draggable_context?.element
  if (!movedGroup) return

  // Check if item was moved to a different container (cross-grid move)
  const isCrossGridMove = event.from !== event.to

  if (isCrossGridMove) {
    // Find the target grid - it's the one that now contains this group
    const targetGrid = grids.value.find(g =>
      g.groups && g.groups.some(grp => grp.id === movedGroup.id)
    )

    if (targetGrid && targetGrid.id !== movedGroup.grid_id) {
      // Update the group's grid_id on the server
      try {
        const response = await fetchWithAuth(`/api/groups/${movedGroup.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: movedGroup.name,
            mode: movedGroup.mode,
            enabled: movedGroup.enabled,
            master_universe: movedGroup.master_universe || null,
            master_channel: movedGroup.master_channel || null,
            color: movedGroup.color || null,
            grid_id: targetGrid.id
          })
        })
        if (!response.ok) {
          console.error('Failed to move group to new grid:', response.status)
          await loadGrids()
          return
        }
        // Update local reference
        movedGroup.grid_id = targetGrid.id
      } catch (e) {
        console.error('Failed to move group to new grid:', e)
        await loadGrids()
        return
      }

      // Update positions in the target grid
      const targetOrderedIds = targetGrid.groups.map(g => g.id)
      try {
        await fetchWithAuth('/api/groups/reorder', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group_ids: targetOrderedIds })
        })
      } catch (e) {
        console.error('Failed to reorder groups in target grid:', e)
      }
    }
  } else {
    // Same grid reorder - just update positions
    const orderedIds = sourceGrid.groups.map(g => g.id)
    try {
      const response = await fetchWithAuth('/api/groups/reorder', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ group_ids: orderedIds })
      })
      if (!response.ok) {
        console.error('Failed to reorder groups:', response.status)
      }
    } catch (e) {
      console.error('Failed to reorder groups:', e)
    }
  }

  // Always reload to sync state with server
  await loadGrids()
}

async function onGridDragEnd() {
  // Get IDs from the displayed grids (which were actually reordered)
  const orderedIds = displayedGrids.value.map(g => g.id)
  try {
    await fetchWithAuth('/api/groups/grids/reorder', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ grid_ids: orderedIds })
    })
    await loadGrids()  // Reload to sync state
  } catch (e) {
    console.error('Failed to reorder grids:', e)
    await loadGrids()
  }
}

async function loadGrids() {
  try {
    const response = await fetchWithAuth('/api/groups/grids')
    const data = await response.json()
    grids.value = data.grids || []

    // Initialize group values from stored master_value
    for (const grid of grids.value) {
      for (const group of grid.groups || []) {
        groupValues[group.id] = group.master_value || 0
      }
    }

    // Set default grid_id for new groups
    if (grids.value.length > 0) {
      groupForm.value.grid_id = grids.value[0].id
    }

    // Then fetch current runtime values (may differ from DB)
    await loadRuntimeValues()

    // Initialize color mixer states from current channel values
    initAllColorMixerStates()
  } catch (e) {
    console.error('Failed to load grids:', e)
  }
}

async function loadRuntimeValues() {
  try {
    const response = await fetchWithAuth('/api/groups/runtime-values')
    const data = await response.json()
    // Override with runtime values
    for (const [groupId, value] of Object.entries(data.values || {})) {
      groupValues[parseInt(groupId)] = value
    }
  } catch (e) {
    console.error('Failed to load runtime group values:', e)
  }
}

async function selectGroup(group) {
  selectedGridForEdit.value = null  // Deselect grid when selecting group
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
  // In single grid mode, auto-select the current grid
  const targetGridId = singleGridMode.value && currentGridId.value
    ? currentGridId.value
    : (grids.value[0]?.id || null)

  groupForm.value = {
    name: '',
    mode: 'proportional',
    enabled: true,
    grid_id: targetGridId
  }
  showAddGroup.value = true
}

function closeGroupModal() {
  showAddGroup.value = false
}

async function createGroup() {
  try {
    // Parse comma-separated names
    const names = groupForm.value.name.split(',')
      .map(n => n.trim())
      .filter(n => n !== '')

    for (const name of names) {
      const response = await fetchWithAuth('/api/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name,
          mode: groupForm.value.mode,
          enabled: groupForm.value.enabled,
          grid_id: groupForm.value.grid_id
        })
      })

      if (!response.ok) {
        const error = await response.json()
        console.error('Failed to create group:', response.status, error)
        alert('Failed to create group "' + name + '": ' + (error.detail || 'Unknown error'))
        // Continue creating remaining groups
      }
    }

    closeGroupModal()
    await loadGrids()
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
    await loadGrids()
    // Update selected group reference
    const allGroups = grids.value.flatMap(g => g.groups || [])
    selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
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
    await loadGrids()
  } catch (e) {
    console.error('Failed to delete group:', e)
  }
}

async function addMember() {
  if (!selectedGroup.value || !canAddMember.value) return

  const targetType = newMember.value.target_type

  if (targetType === 'channel') {
    // Parse comma-separated channels (e.g., "1,2,3")
    const channelStr = String(newMember.value.channel || '')
    const channels = channelStr.split(',').map(s => parseInt(s.trim())).filter(n => !isNaN(n) && n >= 1 && n <= 512)

    // Add each channel
    for (const channel of channels) {
      const memberData = {
        target_type: 'channel',
        universe_id: newMember.value.universe_id,
        channel: channel,
        base_value: newMember.value.base_value,
        color_role: newMember.value.color_role || null
      }

      try {
        await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(memberData)
        })
      } catch (e) {
        console.error('Failed to add member:', e)
      }
    }

    // Refresh and set next channel after the highest added
    await loadGrids()
    const allGroups = grids.value.flatMap(g => g.groups || [])
    selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
    newMember.value.channel = String(Math.max(...channels) + 1)
  } else {
    // Handle universe_master and global_master (single add)
    const memberData = {
      target_type: targetType,
      base_value: newMember.value.base_value,
      color_role: newMember.value.color_role || null
    }

    if (targetType === 'universe_master') {
      memberData.target_universe_id = newMember.value.target_universe_id
    }

    try {
      await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(memberData)
      })
      await loadGrids()
      const allGroups = grids.value.flatMap(g => g.groups || [])
      selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
    } catch (e) {
      console.error('Failed to add member:', e)
    }
  }
}

async function removeMember(member) {
  if (!selectedGroup.value) return

  try {
    await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members/${member.id}`, {
      method: 'DELETE'
    })
    await loadGrids()
    const allGroups = grids.value.flatMap(g => g.groups || [])
    selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
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
        base_value: newValue,
        color_role: member.color_role
      })
    })
    await loadGrids()
    const allGroups = grids.value.flatMap(g => g.groups || [])
    selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
  } catch (e) {
    console.error('Failed to update member:', e)
  }
  editingMember.value = null
}

async function updateMemberColorRole(member, colorRole) {
  if (!selectedGroup.value) return

  try {
    await fetchWithAuth(`/api/groups/${selectedGroup.value.id}/members/${member.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        universe_id: member.universe_id,
        channel: member.channel,
        base_value: member.base_value,
        target_type: member.target_type,
        target_universe_id: member.target_universe_id,
        color_role: colorRole || null
      })
    })
    await loadGrids()
    const allGroups = grids.value.flatMap(g => g.groups || [])
    selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
  } catch (e) {
    console.error('Failed to update member color role:', e)
  }
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
    await loadGrids()
    const allGroups = grids.value.flatMap(g => g.groups || [])
    selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
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

// Input Link picker tile style helpers
function getInputLinkTileStyle(channel) {
  if (inputLinkPicker.value.channel === channel) return {}
  const color = dmxStore.getChannelColor(inputLinkPicker.value.universe_id, channel)
  if (color && color !== 'var(--accent)') {
    return { backgroundColor: color + '40' }
  }
  return {}
}

function getInputLinkGroupColor(channel) {
  return dmxStore.getChannelGroupColor(inputLinkPicker.value.universe_id, channel)
}

function hasInputLinkSameGroupColorLeft(channel) {
  if (channel <= 1) return false
  const current = getInputLinkGroupColor(channel)
  const left = getInputLinkGroupColor(channel - 1)
  return current && left && current === left
}

function hasInputLinkSameGroupColorRight(channel) {
  if (channel >= 512) return false
  const current = getInputLinkGroupColor(channel)
  const right = getInputLinkGroupColor(channel + 1)
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
      await loadGrids()
      const allGroups = grids.value.flatMap(g => g.groups || [])
      selectedGroup.value = allGroups.find(g => g.id === selectedGroup.value.id)
    } else {
      const error = await response.json()
      alert('Failed to add members: ' + (error.detail || 'Unknown error'))
    }
  } catch (e) {
    console.error('Failed to add bulk members:', e)
    alert('Failed to add members: ' + e.message)
  }
}

// Input Link Channel Picker functions
function openInputLinkPicker() {
  inputLinkPicker.value.universe_id = editForm.value.master_universe || universes.value[0]?.id || 1
  inputLinkPicker.value.channel = editForm.value.master_channel || null
  showInputLinkPicker.value = true
}

function closeInputLinkPicker() {
  showInputLinkPicker.value = false
}

function selectInputLinkChannel(ch) {
  inputLinkPicker.value.channel = ch
}

function applyInputLinkChannel() {
  if (!inputLinkPicker.value.channel) return
  editForm.value.master_universe = inputLinkPicker.value.universe_id
  editForm.value.master_channel = inputLinkPicker.value.channel
  saveGroupChanges()
  closeInputLinkPicker()
}

// Fader drag handling
function startDrag(event, group) {
  if (!group.enabled) return
  if (isGroupParked(group.id)) return  // Parked groups are locked
  if (isGroupHighlighted(group.id)) return  // Highlighted groups are locked
  // Note: Input-controlled groups will snap back after drag (handled in triggerGroup)
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

// Color mixer fader with long-press for color picker
let colorMixerLongPressTimer = null
const COLOR_MIXER_LONG_PRESS_DELAY = 500 // ms

function startColorMixerDrag(event, group) {
  if (!group.enabled) return
  if (isGroupParked(group.id)) return
  if (isGroupHighlighted(group.id)) return
  event.preventDefault()

  const track = event.currentTarget
  const startY = event.touches ? event.touches[0].clientY : event.clientY
  const startValue = groupValues[group.id] || 0
  let hasDragged = false

  // Start long-press timer
  colorMixerLongPressTimer = setTimeout(() => {
    if (!hasDragged) {
      // Long press detected - open modal
      openColorPickerModal(group)
    }
    colorMixerLongPressTimer = null
  }, COLOR_MIXER_LONG_PRESS_DELAY)

  function onMove(e) {
    e.preventDefault()
    hasDragged = true

    // Cancel long-press if user is dragging
    if (colorMixerLongPressTimer) {
      clearTimeout(colorMixerLongPressTimer)
      colorMixerLongPressTimer = null
    }

    const rect = track.getBoundingClientRect()
    const currentY = e.touches ? e.touches[0].clientY : e.clientY
    const y = rect.bottom - currentY
    const height = rect.height
    const newValue = Math.round(Math.max(0, Math.min(255, (y / height) * 255)))

    groupValues[group.id] = newValue
    triggerGroup(group.id, newValue)
  }

  function onEnd() {
    if (colorMixerLongPressTimer) {
      clearTimeout(colorMixerLongPressTimer)
      colorMixerLongPressTimer = null
    }
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onEnd)
    document.removeEventListener('touchmove', onMove)
    document.removeEventListener('touchend', onEnd)
    colorMixerDragging.value = null  // Clear tracking on normal end
  }

  // Cancel function for external cancellation (e.g., when IO input overrides)
  function cancelDrag() {
    if (colorMixerLongPressTimer) {
      clearTimeout(colorMixerLongPressTimer)
      colorMixerLongPressTimer = null
    }
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onEnd)
    document.removeEventListener('touchmove', onMove)
    document.removeEventListener('touchend', onEnd)
    colorMixerDragging.value = null
  }

  // Track this drag for external cancellation
  colorMixerDragging.value = { groupId: group.id, cancel: cancelDrag }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onEnd)
  document.addEventListener('touchmove', onMove)
  document.addEventListener('touchend', onEnd)
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
      const response = await fetchWithAuth(`/api/groups/${groupId}/trigger?value=${value}`, {
        method: 'POST'
      })
      if (!response.ok) {
        // API rejected (e.g., input-controlled) - snap back to actual value
        await loadRuntimeValues()
      }
    } catch (e) {
      console.error('Failed to trigger group:', e)
      // Snap back on error
      await loadRuntimeValues()
    }
  }, 30)  // 30ms debounce
}

// Group Park/Highlight handling
const LONG_PRESS_DURATION = 500  // ms

// Park button long-press handling
const groupParkPressTimers = ref({})
const groupParkPressStarted = ref({})

function startGroupParkPress(group) {
  groupParkPressStarted.value[group.id] = Date.now()
  groupParkPressTimers.value[group.id] = setTimeout(async () => {
    try {
      if (isGroupParked(group.id)) {
        await dmxStore.unparkGroup(group.id)
      } else {
        await dmxStore.parkGroup(group.id)
      }
    } catch (e) {
      console.error('Group park error:', e)
    }
    delete groupParkPressStarted.value[group.id]
    delete groupParkPressTimers.value[group.id]
  }, LONG_PRESS_DURATION)
}

function endGroupParkPress(group) {
  const timer = groupParkPressTimers.value[group.id]
  if (timer) {
    clearTimeout(timer)
    delete groupParkPressTimers.value[group.id]
  }

  // Short click on parked group = unpark
  const startTime = groupParkPressStarted.value[group.id]
  if (startTime && Date.now() - startTime < LONG_PRESS_DURATION) {
    if (isGroupParked(group.id)) {
      dmxStore.unparkGroup(group.id)
    }
  }
  delete groupParkPressStarted.value[group.id]
}

function cancelGroupParkPress(group) {
  const timer = groupParkPressTimers.value[group.id]
  if (timer) {
    clearTimeout(timer)
    delete groupParkPressTimers.value[group.id]
  }
  delete groupParkPressStarted.value[group.id]
}

// Highlight button long-press handling
const groupHighlightPressTimers = ref({})
const groupHighlightPressStarted = ref({})

function startGroupHighlightPress(group) {
  groupHighlightPressStarted.value[group.id] = Date.now()
  groupHighlightPressTimers.value[group.id] = setTimeout(async () => {
    try {
      if (isGroupHighlighted(group.id)) {
        await dmxStore.stopHighlightGroup(group.id)
      } else {
        await dmxStore.highlightGroup(group.id)
      }
    } catch (e) {
      console.error('Group highlight error:', e)
    }
    delete groupHighlightPressStarted.value[group.id]
    delete groupHighlightPressTimers.value[group.id]
  }, LONG_PRESS_DURATION)
}

function endGroupHighlightPress(group) {
  const timer = groupHighlightPressTimers.value[group.id]
  if (timer) {
    clearTimeout(timer)
    delete groupHighlightPressTimers.value[group.id]
  }

  // Short click on highlighted group = stop highlight
  const startTime = groupHighlightPressStarted.value[group.id]
  if (startTime && Date.now() - startTime < LONG_PRESS_DURATION) {
    if (isGroupHighlighted(group.id)) {
      dmxStore.stopHighlightGroup(group.id)
    }
  }
  delete groupHighlightPressStarted.value[group.id]
}

function cancelGroupHighlightPress(group) {
  const timer = groupHighlightPressTimers.value[group.id]
  if (timer) {
    clearTimeout(timer)
    delete groupHighlightPressTimers.value[group.id]
  }
  delete groupHighlightPressStarted.value[group.id]
}

// Get display value for group fader (255 when highlighted, otherwise actual value)
function getGroupDisplayValue(groupId) {
  if (isGroupHighlighted(groupId)) {
    return 255  // Show 100% when highlighted
  }
  return groupValues[groupId] || 0
}

// ========== Color Picker Functions ==========

function getGroupHue(groupId) {
  return colorPickerState[groupId]?.h || 0
}

function getGroupSaturation(groupId) {
  return colorPickerState[groupId]?.s || 100
}

function getGroupLightness(groupId) {
  return colorPickerState[groupId]?.l || 50
}

function getColorCursorStyle(groupId) {
  const h = getGroupHue(groupId)
  const s = getGroupSaturation(groupId)
  const l = getGroupLightness(groupId)
  // Convert HSL back to HSV for cursor position (gradient is HSV-based)
  const { sv, v } = hslToHsv(h, s, l)
  const x = sv
  const y = 100 - v
  return {
    left: `${x}%`,
    top: `${y}%`,
    transform: 'translate(-50%, -50%)'
  }
}

function getGroupColorPreview(groupId) {
  const h = getGroupHue(groupId)
  const s = getGroupSaturation(groupId)
  const l = getGroupLightness(groupId)
  return `hsl(${h}, ${s}%, ${l}%)`
}

function initColorPickerState(groupId) {
  if (!colorPickerState[groupId]) {
    // Default to white (h:0, s:0, l:100)
    colorPickerState[groupId] = { h: 0, s: 0, l: 100 }
  }
}

function initColorPickerStateFromChannels(group) {
  // Use the stored color_state from backend instead of reverse-calculating from RGB
  // Backend stores and returns color_state with group data
  if (group.color_state) {
    colorPickerState[group.id] = {
      h: group.color_state.h || 0,
      s: group.color_state.s || 0,
      l: group.color_state.l !== undefined ? group.color_state.l : 100
    }
  } else {
    // Default to white if no color_state stored
    colorPickerState[group.id] = { h: 0, s: 0, l: 100 }
  }
}

function initAllColorMixerStates() {
  for (const grid of grids.value) {
    for (const group of grid.groups || []) {
      if (group.mode === 'color_mixer') {
        initColorPickerStateFromChannels(group)
      }
    }
  }
}

function startColorPick(event, group) {
  event.preventDefault()
  initColorPickerState(group.id)
  colorPickingGroup.value = group

  const target = event.currentTarget
  handleColorPick(event, group, target)

  const moveHandler = (e) => handleColorPick(e, group, target)
  const stopHandler = () => {
    document.removeEventListener('mousemove', moveHandler)
    document.removeEventListener('mouseup', stopHandler)
    document.removeEventListener('touchmove', moveHandler)
    document.removeEventListener('touchend', stopHandler)
    colorPickingGroup.value = null
  }

  document.addEventListener('mousemove', moveHandler)
  document.addEventListener('mouseup', stopHandler)
  document.addEventListener('touchmove', moveHandler)
  document.addEventListener('touchend', stopHandler)
}

function handleColorPick(event, group, target) {
  if (!target) return

  const rect = target.getBoundingClientRect()
  const clientX = event.touches ? event.touches[0].clientX : event.clientX
  const clientY = event.touches ? event.touches[0].clientY : event.clientY

  let x = (clientX - rect.left) / rect.width * 100
  let y = (clientY - rect.top) / rect.height * 100

  // Clamp values
  x = Math.max(0, Math.min(100, x))
  y = Math.max(0, Math.min(100, y))

  // x = saturation in HSV, y inverted = value in HSV
  const sv = x
  const v = 100 - y
  const { s, l } = hsvToHsl(colorPickerState[group.id].h, sv, v)

  colorPickerState[group.id].s = s
  colorPickerState[group.id].l = l

  applyColorToGroup(group)
}

function updateGroupHue(group, hue) {
  initColorPickerState(group.id)
  colorPickerState[group.id].h = parseInt(hue)
  applyColorToGroup(group)
}

function hslToRgb(h, s, l) {
  h = h / 360
  s = s / 100
  l = l / 100

  let r, g, b

  if (s === 0) {
    r = g = b = l
  } else {
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1
      if (t > 1) t -= 1
      if (t < 1/6) return p + (q - p) * 6 * t
      if (t < 1/2) return q
      if (t < 2/3) return p + (q - p) * (2/3 - t) * 6
      return p
    }

    const q = l < 0.5 ? l * (1 + s) : l + s - l * s
    const p = 2 * l - q
    r = hue2rgb(p, q, h + 1/3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1/3)
  }

  return {
    r: Math.round(r * 255),
    g: Math.round(g * 255),
    b: Math.round(b * 255)
  }
}

function colorRoleToValue(role, rgb) {
  const { r, g, b } = rgb

  switch (role) {
    case 'red': return r
    case 'green': return g
    case 'blue': return b
    case 'white':
    case 'warm_white':
    case 'cool_white':
      // White is the minimum of RGB (color subtraction approach)
      return Math.min(r, g, b)
    case 'amber':
      // Amber is warm orange - mix of red and some green
      return Math.round(Math.min(r, g * 0.5) * 0.8)
    case 'orange':
      // Orange is between red and yellow
      return Math.round((r + Math.min(r, g)) / 2 * 0.7)
    case 'yellow':
      // Yellow is minimum of red and green
      return Math.min(r, g)
    case 'cyan':
      // Cyan is minimum of green and blue
      return Math.min(g, b)
    case 'magenta':
      // Magenta is minimum of red and blue
      return Math.min(r, b)
    case 'lime':
      // Lime is greenish-yellow
      return Math.round((g + Math.min(r, g)) / 2)
    case 'uv':
      // UV is triggered by blue/violet tones
      return Math.round(b * 0.7)
    default:
      return 0
  }
}

// Debounce timers for color sync to backend
const colorSyncTimers = {}

async function syncColorToBackend(groupId, h, s, l) {
  // Debounce color sync to avoid too many API calls during dragging
  if (colorSyncTimers[groupId]) {
    clearTimeout(colorSyncTimers[groupId])
  }

  colorSyncTimers[groupId] = setTimeout(async () => {
    try {
      await fetchWithAuth(`/api/groups/${groupId}/color`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ h, s, l })
      })
    } catch (e) {
      console.error('Failed to sync color to backend:', e)
    }
  }, 50)  // 50ms debounce
}

async function applyColorToGroup(group) {
  if (!group.members || group.members.length === 0) return

  const state = colorPickerState[group.id]
  if (!state) return

  // Sync color state to backend (backend will calculate and apply RGB)
  syncColorToBackend(group.id, state.h, state.s, state.l)

  const rgb = hslToRgb(state.h, state.s, state.l)

  // Update modal RGB display if modal is open for this group
  if (colorPickerModal.value.visible && colorPickerModal.value.group?.id === group.id) {
    colorPickerModal.value.rgb = { ...rgb }
  }
}

// ========== Color Picker Modal Functions ==========

function openColorPickerModal(group) {
  initColorPickerStateFromChannels(group)
  const state = colorPickerState[group.id]
  const rgb = hslToRgb(state.h, state.s, state.l)

  // Set default brightness if not set
  if (groupValues[group.id] === undefined) {
    groupValues[group.id] = 100
  }

  colorPickerModal.value = {
    visible: true,
    group: group,
    rgb: rgb,
    brightness: groupValues[group.id]
  }

  // DON'T call applyColorToGroup() here - just setting up UI
  // Color will be synced when user actually picks a color
}

function closeColorPickerModal() {
  colorPickerModal.value.visible = false
}

function startColorPickModal(event) {
  if (!colorPickerModal.value.group) return
  event.preventDefault()

  const target = event.currentTarget
  handleColorPickModal(event, target)

  const moveHandler = (e) => handleColorPickModal(e, target)
  const stopHandler = () => {
    document.removeEventListener('mousemove', moveHandler)
    document.removeEventListener('mouseup', stopHandler)
    document.removeEventListener('touchmove', moveHandler)
    document.removeEventListener('touchend', stopHandler)
  }

  document.addEventListener('mousemove', moveHandler)
  document.addEventListener('mouseup', stopHandler)
  document.addEventListener('touchmove', moveHandler)
  document.addEventListener('touchend', stopHandler)
}

function handleColorPickModal(event, target) {
  const group = colorPickerModal.value.group
  if (!group || !target) return

  const rect = target.getBoundingClientRect()
  const clientX = event.touches ? event.touches[0].clientX : event.clientX
  const clientY = event.touches ? event.touches[0].clientY : event.clientY

  let x = (clientX - rect.left) / rect.width * 100
  let y = (clientY - rect.top) / rect.height * 100

  x = Math.max(0, Math.min(100, x))
  y = Math.max(0, Math.min(100, y))

  // x = saturation in HSV, y inverted = value in HSV
  const sv = x
  const v = 100 - y
  const { s, l } = hsvToHsl(colorPickerState[group.id].h, sv, v)

  colorPickerState[group.id].s = s
  colorPickerState[group.id].l = l

  applyColorToGroup(group)
}

function updateGroupHueModal(hue) {
  const group = colorPickerModal.value.group
  if (!group) return

  initColorPickerState(group.id)
  colorPickerState[group.id].h = parseInt(hue)
  applyColorToGroup(group)
}

function updateRgbValue(channel, value) {
  const v = Math.max(0, Math.min(255, parseInt(value) || 0))
  colorPickerModal.value.rgb[channel] = v

  const { r, g, b } = colorPickerModal.value.rgb
  const hsl = rgbToHsl(r, g, b)

  const group = colorPickerModal.value.group
  if (!group) return

  colorPickerState[group.id] = { h: hsl.h, s: hsl.s, l: hsl.l }
  applyColorToGroup(group)
}

function updateBrightness(value) {
  const brightness = Math.max(0, Math.min(255, parseInt(value) || 0))
  colorPickerModal.value.brightness = brightness

  const group = colorPickerModal.value.group
  if (group) {
    // Update the group's master value (used for brightness)
    groupValues[group.id] = brightness
    applyColorToGroup(group)
    // Notify backend so fader updates and value persists
    triggerGroup(group.id, brightness)
  }
}

function rgbToHsl(r, g, b) {
  r /= 255
  g /= 255
  b /= 255

  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  let h, s
  const l = (max + min) / 2

  if (max === min) {
    h = s = 0
  } else {
    const d = max - min
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
    switch (max) {
      case r: h = ((g - b) / d + (g < b ? 6 : 0)) / 6; break
      case g: h = ((b - r) / d + 2) / 6; break
      case b: h = ((r - g) / d + 4) / 6; break
    }
  }

  return { h: h * 360, s: s * 100, l: l * 100 }
}

function hsvToHsl(h, sv, v) {
  // sv and v are 0-100
  sv /= 100
  v /= 100

  const l = v * (1 - sv / 2)
  let sl = 0
  if (l > 0 && l < 1) {
    sl = (v - l) / Math.min(l, 1 - l)
  }

  return { h, s: sl * 100, l: l * 100 }
}

function hslToHsv(h, s, l) {
  // s and l are 0-100
  s /= 100
  l /= 100

  const v = l + s * Math.min(l, 1 - l)
  let sv = 0
  if (v > 0) {
    sv = 2 * (1 - l / v)
  }

  return { h, sv: sv * 100, v: v * 100 }
}

// ========== End Color Picker Functions ==========

// Check if all channel members of a group are parked
function isGroupParked(groupId) {
  const group = getAllGroups.value.find(g => g.id === groupId)
  if (!group || !group.members) return false

  const channelMembers = group.members.filter(m => m.target_type === 'channel')
  if (channelMembers.length === 0) return false

  return channelMembers.every(m =>
    dmxStore.isChannelParked(m.universe_id, m.channel)
  )
}

// Check if all channel members of a group are highlighted
function isGroupHighlighted(groupId) {
  const group = getAllGroups.value.find(g => g.id === groupId)
  if (!group || !group.members) return false

  const channelMembers = group.members.filter(m => m.target_type === 'channel')
  if (channelMembers.length === 0) return false

  return channelMembers.every(m =>
    dmxStore.isChannelHighlighted(m.universe_id, m.channel)
  )
}
</script>

<style scoped>
.input-hint {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
  display: block;
}

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

.single-grid-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.single-grid-header .card-title {
  flex: 1;
}

.single-grid-header .header-actions-row {
  margin-left: auto;
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

/* Grids Container */
.grids-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: auto;
}

.group-grid {
  display: flex;
  flex-direction: row;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  min-height: 180px;
}

.group-grid.single-mode {
  flex: 1;
  min-height: 0;
}

/* Vertical Title Bar */
.grid-title-bar {
  min-width: 40px;
  display: flex;
  background: var(--accent);
  color: white;
  font-weight: 600;
  font-size: 14px;
  cursor: pointer;
  transition: filter 0.2s;
}

.grid-title-content {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  flex: 1;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-between;
  padding: 12px 8px;
}

.grid-title-bar:hover {
  filter: brightness(1.1);
}

.grid-title {
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-height: 150px;
}

.grid-edit-indicator {
  transform: rotate(180deg);
  opacity: 0.7;
}

/* Grid drag handle */
.grid-drag-handle {
  transform: rotate(180deg);
  cursor: grab;
  color: rgba(255, 255, 255, 0.7);
  padding: 4px;
  transition: color 0.2s;
}

.grid-drag-handle:hover {
  color: white;
}

.grid-drag-handle:active {
  cursor: grabbing;
}

/* Grid drag states */
.grid-ghost {
  opacity: 0.4;
  border: 2px dashed var(--accent) !important;
}

.grid-dragging {
  opacity: 0.95;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  z-index: 100;
}

/* Groups grid area */
.groups-grid-container {
  flex: 1;
  padding: 16px;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.groups-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-content: flex-start;
  min-height: 100px;
}

.empty-grid-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--text-secondary);
  font-size: 13px;
  font-style: italic;
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

/* Drag-and-drop styles */
.group-drag-handle {
  position: absolute;
  top: 4px;
  right: 4px;
  padding: 4px;
  cursor: grab;
  color: var(--text-secondary);
  opacity: 0.5;
  transition: opacity 0.2s;
  touch-action: none;
  z-index: 2;
}

.group-drag-handle:active {
  cursor: grabbing;
}

.group-fader:hover .group-drag-handle {
  opacity: 0.8;
}

.group-fader.draggable .group-drag-handle:hover {
  opacity: 1;
  color: var(--accent);
}

.group-fader-ghost {
  opacity: 0.4;
  background: var(--bg-secondary);
  border: 2px dashed var(--accent);
}

.group-fader-dragging {
  opacity: 0.9;
  transform: scale(1.02);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  z-index: 100;
}

.edit-mode-active .groups-grid {
  min-height: 160px;
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

/* Color Picker Styles */
.color-picker-container {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: center;
}

.color-picker-gradient {
  width: 60px;
  height: 60px;
  border-radius: 4px;
  position: relative;
  cursor: crosshair;
  border: 1px solid var(--border);
}

.color-picker-cursor {
  position: absolute;
  width: 10px;
  height: 10px;
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 0 2px rgba(0,0,0,0.5);
  pointer-events: none;
}

.hue-slider {
  width: 60px;
  height: 12px;
  -webkit-appearance: none;
  appearance: none;
  background: linear-gradient(to right,
    hsl(0, 100%, 50%),
    hsl(60, 100%, 50%),
    hsl(120, 100%, 50%),
    hsl(180, 100%, 50%),
    hsl(240, 100%, 50%),
    hsl(300, 100%, 50%),
    hsl(360, 100%, 50%)
  );
  border-radius: 4px;
  outline: none;
  cursor: pointer;
}

.hue-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 10px;
  height: 14px;
  background: white;
  border-radius: 2px;
  cursor: pointer;
  box-shadow: 0 0 2px rgba(0,0,0,0.5);
}

.hue-slider::-moz-range-thumb {
  width: 10px;
  height: 14px;
  background: white;
  border-radius: 2px;
  cursor: pointer;
  box-shadow: 0 0 2px rgba(0,0,0,0.5);
  border: none;
}

.color-preview {
  width: 60px;
  height: 16px;
  border-radius: 4px;
  border: 1px solid var(--border);
}

/* Clickable color preview in group card */
.color-preview-clickable {
  width: 50px;
  height: 100px;
  border-radius: 4px;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: transform 0.1s, box-shadow 0.1s;
}

.color-preview-clickable:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

/* Color Mixer Fader - drag for brightness, long-press for color picker */
.color-mixer-fader {
  width: 30px;
  height: 120px;
  background: var(--bg-tertiary);
  border-radius: 4px;
  border: 3px solid transparent;
  position: relative;
  overflow: hidden;
  cursor: pointer;
  transition: border-color 0.2s;
}

.color-mixer-fader:hover {
  box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

.color-mixer-fill {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: var(--fill-height, 0%);
  transition: height 0.05s ease-out;
  pointer-events: none;
}

/* Color Picker Modal */
.modal-color-picker {
  width: 340px;
}

.color-picker-modal-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: center;
  padding: 16px;
}

.color-picker-gradient-large {
  width: 280px;
  height: 200px;
  border-radius: 8px;
  position: relative;
  cursor: crosshair;
  border: 1px solid var(--border);
}

.color-picker-cursor-large {
  position: absolute;
  width: 14px;
  height: 14px;
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 0 4px rgba(0,0,0,0.5);
  pointer-events: none;
}

.hue-slider-large {
  width: 280px;
  height: 20px;
  -webkit-appearance: none;
  appearance: none;
  background: linear-gradient(to right,
    hsl(0, 100%, 50%),
    hsl(60, 100%, 50%),
    hsl(120, 100%, 50%),
    hsl(180, 100%, 50%),
    hsl(240, 100%, 50%),
    hsl(300, 100%, 50%),
    hsl(360, 100%, 50%)
  );
  border-radius: 10px;
  outline: none;
  cursor: pointer;
}

.hue-slider-large::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 24px;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  box-shadow: 0 0 4px rgba(0,0,0,0.5);
}

.hue-slider-large::-moz-range-thumb {
  width: 14px;
  height: 24px;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  box-shadow: 0 0 4px rgba(0,0,0,0.5);
  border: none;
}

.rgb-inputs {
  display: flex;
  gap: 16px;
}

.rgb-input-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.rgb-input-group label {
  font-weight: 600;
  font-size: 14px;
  color: var(--text-primary);
}

.rgb-input-group input {
  width: 70px;
  text-align: center;
  padding: 8px;
}

.color-preview-large {
  width: 280px;
  height: 50px;
  border-radius: 8px;
  border: 1px solid var(--border);
}

.brightness-section {
  width: 280px;
}

.brightness-section .form-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
}

.brightness-slider-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brightness-slider {
  flex: 1;
  height: 20px;
  -webkit-appearance: none;
  appearance: none;
  background: linear-gradient(to right, #000, #fff);
  border-radius: 10px;
  outline: none;
  cursor: pointer;
}

.brightness-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 24px;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  box-shadow: 0 0 4px rgba(0,0,0,0.5);
}

.brightness-slider::-moz-range-thumb {
  width: 14px;
  height: 24px;
  background: white;
  border-radius: 4px;
  cursor: pointer;
  box-shadow: 0 0 4px rgba(0,0,0,0.5);
  border: none;
}

.brightness-value {
  min-width: 36px;
  text-align: right;
  font-weight: 600;
}

.color-role-select {
  font-size: 10px;
  padding: 2px 4px;
  min-width: 60px;
  max-width: 80px;
}

/* Color role badges */
.member-row .color-role-select {
  flex-shrink: 0;
}

.group-controls-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}

.group-value {
  font-size: 12px;
  font-weight: bold;
  color: var(--text-primary);
}

.park-btn,
.highlight-btn {
  width: 18px;
  height: 18px;
  font-size: 10px;
  font-weight: bold;
  border: none;
  border-radius: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  transition: all 0.15s ease;
  user-select: none;
  -webkit-user-select: none;
  touch-action: manipulation;
}

.park-btn:hover,
.highlight-btn:hover {
  background: var(--bg-elevated);
}

.park-btn.active {
  background: #f59e0b;
  color: #000;
}

.highlight-btn.active {
  background: #3b82f6;
  color: #fff;
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

.mode-badge.color_mixer {
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.2), rgba(34, 197, 94, 0.2), rgba(59, 130, 246, 0.2));
  color: #f472b6;
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

.input-link-channel-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.input-link-channel-row .form-input {
  flex: 1;
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
  min-width: 60px;
  font-size: 12px;
  padding: 6px 8px;
}

.add-member-row .form-input {
  min-width: 70px;
}

.input-separator {
  color: var(--text-secondary);
  font-size: 12px;
  padding: 0 2px;
}

.members-list {
  /* No max-height or overflow - let it grow naturally */
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

.danger-zone .help-text {
  margin-top: 8px;
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

/* Target type select in add member row */
.add-member-row .target-type-select {
  min-width: 115px;
  max-width: 115px;
  flex: 0 0 115px !important;
}

/* When Channel is selected, put target-type-select on its own line */
.add-member-row--channel {
  flex-wrap: wrap;
}

.add-member-row--channel .target-type-select {
  width: 100%;
  max-width: none;
  flex: none !important;
  margin-bottom: 4px;
}

/* Master target display in member list */
.master-target {
  color: var(--accent);
  font-weight: 600;
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

/* Header actions row */
.header-actions-row {
  display: flex;
  align-items: center;
  gap: 12px;
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

/* Single grid view */
.single-grid-view .grids-container {
  flex: 1;
}

.single-grid-view .group-grid {
  flex: 1;
}

.single-grid-view .groups-grid-container {
  flex: 1;
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

  /* Keep title bar on side for mobile, but narrower */
  .group-grid {
    flex-direction: row;
  }

  .grid-title-bar {
    min-width: 28px;
    max-width: 28px;
    padding: 8px 4px;
  }

  .grid-title-content {
    padding: 8px 4px;
  }

  .grid-title {
    font-size: 12px;
    max-height: 120px;
  }

  .grid-edit-indicator {
    font-size: 10px;
  }

  .grid-drag-handle {
    font-size: 10px;
  }

  .single-grid-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .single-grid-header .header-actions-row {
    margin-left: 0;
    width: 100%;
    justify-content: space-between;
  }
}
</style>

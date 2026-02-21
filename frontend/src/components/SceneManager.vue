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
            <th class="drag-col"></th>
            <th>Name</th>
            <th>Transition</th>
            <th>Duration</th>
            <th>Channels</th>
            <th>Groups</th>
            <th>Masters</th>
            <th>Actions</th>
          </tr>
        </thead>
        <draggable
          v-model="filteredScenes"
          tag="tbody"
          item-key="id"
          :animation="200"
          ghost-class="scene-row-ghost"
          drag-class="scene-row-dragging"
          handle=".drag-handle"
          :delay="150"
          :delay-on-touch-only="true"
          :touch-start-threshold="5"
          filter=".action-buttons"
          :prevent-on-filter="false"
          @end="onDragEnd"
        >
          <template #item="{ element: scene }">
            <tr>
              <td class="drag-handle">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <circle cx="9" cy="6" r="2"/><circle cx="15" cy="6" r="2"/>
                  <circle cx="9" cy="12" r="2"/><circle cx="15" cy="12" r="2"/>
                  <circle cx="9" cy="18" r="2"/><circle cx="15" cy="18" r="2"/>
                </svg>
              </td>
              <td class="truncate-mobile">
                <strong>{{ scene.name }}</strong>
              </td>
              <td>
                <span class="transition-badge">{{ scene.transition_type }}</span>
              </td>
              <td>{{ scene.duration > 0 ? `${scene.duration}ms` : '-' }}</td>
              <td>{{ scene.values?.length || 0 }}</td>
              <td>{{ scene.group_values?.length || 0 }}</td>
              <td>
                <span v-if="getMasterIndicators(scene)" class="master-indicators" :title="getMasterIndicatorsTitle(scene)">
                  {{ getMasterIndicators(scene) }}
                </span>
                <span v-else class="no-masters">-</span>
              </td>
              <td class="action-buttons">
                <button class="btn btn-small btn-primary" @click="recallScene(scene)">Recall</button>
                <button class="btn btn-small btn-secondary" @click="editScene(scene)">Edit</button>
                <button class="btn btn-small btn-secondary" @click="editSceneValues(scene)">Values</button>
                <button class="btn btn-small btn-secondary" @click="updateSceneValues(scene)">Update</button>
                <button class="btn btn-small btn-danger" @click="confirmDeleteScene(scene)">Delete</button>
              </td>
            </tr>
          </template>
          <template #footer>
            <tr v-if="filteredScenes.length === 0">
              <td colspan="8" style="text-align: center; color: var(--text-secondary); padding: 40px;">
                No scenes available. Click "+ New Scene" to create your first scene.
              </td>
            </tr>
          </template>
        </draggable>
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

        <!-- Group Selection (only for new scenes) -->
        <div v-if="!editingScene && groups.length > 0" class="form-group">
          <label class="form-label">Group Faders to Capture</label>
          <template v-if="enabledGroups.length > 0">
            <div class="universe-select-header">
              <button type="button" class="btn btn-small btn-secondary" @click="selectedGroups = enabledGroups.map(g => g.id)">All</button>
              <button type="button" class="btn btn-small btn-secondary" @click="selectedGroups = []">None</button>
            </div>
            <div class="universe-checkboxes">
              <label
                v-for="g in enabledGroups"
                :key="g.id"
                class="universe-checkbox group-checkbox"
                :class="{ selected: selectedGroups.includes(g.id) }"
              >
                <input
                  type="checkbox"
                  :checked="selectedGroups.includes(g.id)"
                  @change="toggleGroup(g.id)"
                >
                <span class="checkbox-label">{{ g.name }}</span>
              </label>
            </div>
          </template>
          <p v-else style="color: var(--text-secondary); font-size: 13px;">
            No enabled groups. Enable groups in the Groups page to include them in scenes.
          </p>
        </div>

        <!-- Master Values Capture (only for new scenes) -->
        <div v-if="!editingScene" class="form-group">
          <label class="form-label">Master Faders to Capture</label>
          <div class="master-checkboxes">
            <label class="master-checkbox" :class="{ selected: includeGlobalMaster }">
              <input type="checkbox" v-model="includeGlobalMaster">
              <span>Global Master</span>
            </label>
            <label class="master-checkbox" :class="{ selected: includeUniverseMasters }">
              <input type="checkbox" v-model="includeUniverseMasters">
              <span>Universe Masters</span>
            </label>
          </div>
          <p class="help-text">Master fader values will be recalled along with channel values.</p>
        </div>

        <div v-if="!editingScene" class="form-group">
          <p style="color: var(--text-secondary); font-size: 13px;">
            This will save the current fader values from the selected universe(s) as a new scene.
            <template v-if="selectedGroups.length > 0">
              <br>Also captures {{ selectedGroups.length }} group fader{{ selectedGroups.length > 1 ? 's' : '' }}.
            </template>
            <template v-if="includeGlobalMaster || includeUniverseMasters">
              <br>Also captures {{ includeGlobalMaster ? 'Global Master' : '' }}{{ includeGlobalMaster && includeUniverseMasters ? ' and ' : '' }}{{ includeUniverseMasters ? 'Universe Masters' : '' }}.
            </template>
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

        <!-- Group Faders Selection -->
        <div v-if="enabledGroups.length > 0" class="form-group">
          <label class="form-label">Group Faders to Capture</label>
          <div class="universe-select-header">
            <button type="button" class="btn btn-small btn-secondary" @click="updateSelectedGroups = enabledGroups.map(g => g.id)">All</button>
            <button type="button" class="btn btn-small btn-secondary" @click="updateSelectedGroups = []">None</button>
          </div>
          <div class="universe-checkboxes">
            <label
              v-for="g in enabledGroups"
              :key="g.id"
              class="universe-checkbox group-checkbox"
              :class="{ selected: updateSelectedGroups.includes(g.id) }"
            >
              <input
                type="checkbox"
                :checked="updateSelectedGroups.includes(g.id)"
                @change="toggleUpdateGroup(g.id)"
              >
              <span class="checkbox-label">{{ g.name }}</span>
            </label>
          </div>
        </div>

        <!-- Master Values Capture -->
        <div class="form-group">
          <label class="form-label">Master Faders to Capture</label>
          <div class="master-checkboxes">
            <label class="master-checkbox" :class="{ selected: updateIncludeGlobalMaster }">
              <input type="checkbox" v-model="updateIncludeGlobalMaster">
              <span>Global Master</span>
            </label>
            <label class="master-checkbox" :class="{ selected: updateIncludeUniverseMasters }">
              <input type="checkbox" v-model="updateIncludeUniverseMasters">
              <span>Universe Masters</span>
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
          <template v-if="updateIncludeGlobalMaster || updateIncludeUniverseMasters">
            <br>Master faders ({{ updateIncludeGlobalMaster ? 'Global' : '' }}{{ updateIncludeGlobalMaster && updateIncludeUniverseMasters ? ', ' : '' }}{{ updateIncludeUniverseMasters ? 'Universe' : '' }}) will also be updated.
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
              <button
                class="universe-tab groups-tab"
                :class="{ active: activeValueTab === 'groups' }"
                @click="activeValueTab = 'groups'"
              >
                Groups ({{ editGroupValuesForm.length }})
              </button>
              <button
                class="universe-tab masters-tab"
                :class="{ active: activeValueTab === 'masters' }"
                @click="activeValueTab = 'masters'"
              >
                Masters ({{ editMasterValuesForm.length }})
              </button>
            </div>
            <div class="universe-tabs-actions" v-if="activeValueTab !== 'groups' && activeValueTab !== 'masters'">
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

          <!-- Channel Values Section (for universe tabs) -->
          <template v-if="activeValueTab !== 'groups' && activeValueTab !== 'masters'">
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
                v-for="(val, index) in getValuesForUniverse(activeValueTab)"
                :key="`${activeValueTab}-${index}`"
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
          </template>

          <!-- Group Values Section (for groups tab) -->
          <template v-else-if="activeValueTab === 'groups'">
            <div class="values-header values-header-tabbed group-values-header">
              <span>Group</span>
              <span>Master Value</span>
              <span>Color</span>
              <span></span>
            </div>
            <div class="values-list">
              <div
                v-for="(gv, index) in editGroupValuesForm"
                :key="`group-${gv.group_id}-${index}`"
                class="value-row value-row-tabbed group-value-row"
              >
                <span class="group-name-cell">{{ getGroupName(gv.group_id) }}</span>
                <input type="number" class="form-input" v-model.number="gv.master_value" min="0" max="255">
                <span
                  v-if="isColorMixerGroup(gv.group_id) && gv.color_state_h != null"
                  class="color-preview-small color-preview-clickable"
                  :style="{ background: getHslColor(gv) }"
                  :title="`H:${Math.round(gv.color_state_h)} S:${Math.round(gv.color_state_s)}% L:${Math.round(gv.color_state_l)}% - Click to edit`"
                  @click="openSceneColorPicker(gv)"
                ></span>
                <span
                  v-else-if="isColorMixerGroup(gv.group_id)"
                  class="color-preview-small color-preview-none color-preview-clickable"
                  title="Click to add color"
                  @click="openSceneColorPicker(gv)"
                >+</span>
                <span v-else class="color-preview-placeholder"></span>
                <button type="button" class="btn btn-small btn-danger" @click="removeGroupValue(index)">X</button>
              </div>
              <div v-if="editGroupValuesForm.length === 0" style="padding: 20px; text-align: center; color: var(--text-secondary);">
                No group values stored in this scene.
              </div>
            </div>
            <div style="margin-top: 8px;">
              <select class="form-select" v-model="addGroupId" style="width: auto; display: inline-block; margin-right: 8px;">
                <option :value="null" disabled>Select group...</option>
                <option v-for="g in availableGroupsToAdd" :key="g.id" :value="g.id">{{ g.name }}</option>
              </select>
              <button type="button" class="btn btn-small btn-secondary" @click="addGroupValue" :disabled="!addGroupId">
                + Add Group
              </button>
            </div>
          </template>

          <!-- Master Values Section (for masters tab) -->
          <template v-else-if="activeValueTab === 'masters'">
            <div class="values-header values-header-tabbed group-values-header">
              <span>Master</span>
              <span>Value</span>
              <span></span>
            </div>
            <div class="values-list">
              <div
                v-for="(mv, index) in editMasterValuesForm"
                :key="`master-${mv.master_type}-${mv.universe_id || 'global'}-${index}`"
                class="value-row value-row-tabbed group-value-row"
              >
                <span class="group-name-cell">{{ mv.master_type === 'global' ? 'Global Master' : getUniverseMasterLabel(mv.universe_id) }}</span>
                <input type="number" class="form-input" v-model.number="mv.value" min="0" max="255">
                <button type="button" class="btn btn-small btn-danger" @click="removeMasterValue(index)">X</button>
              </div>
              <div v-if="editMasterValuesForm.length === 0" style="padding: 20px; text-align: center; color: var(--text-secondary);">
                No master values stored in this scene.
              </div>
            </div>
            <div style="margin-top: 8px;">
              <select class="form-select" v-model="newMasterType" style="width: auto; display: inline-block; margin-right: 8px;">
                <option value="" disabled>Select master...</option>
                <option value="global" :disabled="hasGlobalMaster">Global Master</option>
                <option v-for="u in universes" :key="u.id" :value="`universe_${u.id}`" :disabled="hasUniverseMaster(u.id)">
                  {{ u.label }} Master
                </option>
              </select>
              <input type="number" class="form-input" v-model.number="newMasterValue" min="0" max="255" placeholder="255" style="width: 80px; display: inline-block; margin-right: 8px;">
              <button type="button" class="btn btn-small btn-secondary" @click="addMasterValue" :disabled="!newMasterType">
                + Add Master
              </button>
            </div>
          </template>
        </div>

        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="editingValues = null">Cancel</button>
          <button type="button" class="btn btn-primary" @click="saveSceneValues">Save Values</button>
        </div>
      </div>
    </div>

    <!-- Jump Popup -->
    <div v-if="showJumpPopup" class="modal-overlay">
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

    <!-- Scene Color Picker Modal -->
    <div v-if="sceneColorPicker.visible" class="modal-overlay scene-color-overlay">
      <div class="modal scene-color-picker-modal">
        <div class="modal-header">
          <h3 class="modal-title">Edit Color</h3>
        </div>
        <div class="scene-color-picker-content">
          <div
            class="color-picker-area"
            @mousedown="startSceneColorPick"
            @touchstart="startSceneColorPick"
          >
            <div class="color-picker-indicator" :style="{ left: (sceneColorPicker.h / 360 * 100) + '%', top: (100 - sceneColorPicker.s) + '%' }"></div>
          </div>
          <div class="lightness-slider-row">
            <span>L</span>
            <input type="range" v-model.number="sceneColorPicker.l" min="0" max="100" class="lightness-slider">
            <span>{{ Math.round(sceneColorPicker.l) }}%</span>
          </div>
          <div class="color-preview-row">
            <div class="color-preview-large" :style="{ background: `hsl(${sceneColorPicker.h}, ${sceneColorPicker.s}%, ${sceneColorPicker.l}%)` }"></div>
            <div class="color-values">
              H: {{ Math.round(sceneColorPicker.h) }}° S: {{ Math.round(sceneColorPicker.s) }}% L: {{ Math.round(sceneColorPicker.l) }}%
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <button class="btn btn-secondary" @click="closeSceneColorPicker">Cancel</button>
          <button class="btn btn-primary" @click="applySceneColor">Apply</button>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import draggable from 'vuedraggable'
import { useDmxStore } from '../stores/dmx.js'
import { useAuthStore } from '../stores/auth.js'
import { wsManager } from '../websocket.js'

const dmxStore = useDmxStore()
const authStore = useAuthStore()

// Filtered scenes based on user's allowed_scenes permission (writable for draggable)
const filteredScenes = computed({
  get: () => dmxStore.scenes.filter(scene => authStore.hasSceneAccess(scene.id)),
  set: (newValue) => {
    // Update the store with the reordered filtered scenes
    dmxStore.scenes = newValue
  }
})

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

async function onDragEnd(event) {
  // Only process if position actually changed
  if (event.oldIndex === event.newIndex) return

  // Extract ordered IDs from the filtered scenes array
  const orderedIds = filteredScenes.value.map(s => s.id)

  try {
    await fetchWithAuth('/api/scenes/reorder', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scene_ids: orderedIds })
    })
  } catch (e) {
    console.error('Failed to reorder scenes:', e)
    // Reload scenes to restore server state on error
    await dmxStore.loadScenes()
  }
}

const showAddScene = ref(false)
const editingScene = ref(null)
const deletingScene = ref(null)
const updatingScene = ref(null)
const editingValues = ref(null)
const editValuesForm = ref([])
const editGroupValuesForm = ref([])  // [{group_id, master_value}]
const editMasterValuesForm = ref([])  // [{master_type, universe_id?, value}]
const groups = ref([])  // All groups for name lookup
const addGroupId = ref(null)  // For adding a new group to the scene
const newMasterType = ref('')  // For adding new master values
const newMasterValue = ref(255)
const { universes } = storeToRefs(dmxStore)
const bulkMode = ref('add')
const bulkStart = ref(null)
const bulkEnd = ref(null)
const bulkValue = ref(255)
const bulkUniverse = ref(1)

// Universe selection state
const selectedUniverses = ref([])  // For new scene modal
const selectedGroups = ref([])  // For new scene modal - which groups to capture
const updateSelectedUniverses = ref([])  // For update modal
const updateSelectedGroups = ref([])  // For update modal - which groups to capture
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

// Master values capture state
const includeGlobalMaster = ref(false)
const includeUniverseMasters = ref(false)
const updateIncludeGlobalMaster = ref(false)
const updateIncludeUniverseMasters = ref(false)

const canSaveScene = computed(() => {
  if (!sceneForm.value.name) return false
  if (!editingScene.value && selectedUniverses.value.length === 0) return false
  return true
})

onMounted(async () => {
  await dmxStore.loadScenes()
  await dmxStore.loadUniverses()
  await loadGroups()
  initUniverseSelection()
  initGroupSelection()
})

async function loadGroups() {
  try {
    const response = await fetchWithAuth('/api/groups')
    if (response.ok) {
      const data = await response.json()
      // API returns {groups: [...]} not just the array
      groups.value = data.groups || []
    } else {
      groups.value = []
    }
  } catch (e) {
    console.error('SceneManager: Failed to load groups:', e)
    groups.value = []
  }
}

function getGroupName(groupId) {
  if (!groups.value || !Array.isArray(groups.value)) return `Group ${groupId}`
  const group = groups.value.find(g => g.id === groupId)
  return group ? group.name : `Group ${groupId} (deleted)`
}

function getHslColor(gv) {
  const h = gv.color_state_h || 0
  const s = gv.color_state_s || 0
  const l = gv.color_state_l !== undefined ? gv.color_state_l : 100
  return `hsl(${h}, ${s}%, ${l}%)`
}

function isColorMixerGroup(groupId) {
  const group = groups.value.find(g => g.id === groupId)
  return group && group.mode === 'color_mixer'
}

// Scene color picker state
const sceneColorPicker = ref({ visible: false, gv: null, h: 0, s: 100, l: 50 })

function openSceneColorPicker(gv) {
  sceneColorPicker.value = {
    visible: true,
    gv: gv,
    h: gv.color_state_h || 0,
    s: gv.color_state_s !== undefined ? gv.color_state_s : 100,
    l: gv.color_state_l !== undefined ? gv.color_state_l : 50
  }
}

function applySceneColor() {
  const gv = sceneColorPicker.value.gv
  if (gv) {
    gv.color_state_h = sceneColorPicker.value.h
    gv.color_state_s = sceneColorPicker.value.s
    gv.color_state_l = sceneColorPicker.value.l
  }
  closeSceneColorPicker()
}

function closeSceneColorPicker() {
  sceneColorPicker.value.visible = false
}

function handleSceneColorPick(event) {
  const target = event.currentTarget
  const rect = target.getBoundingClientRect()
  const x = (event.touches ? event.touches[0].clientX : event.clientX) - rect.left
  const y = (event.touches ? event.touches[0].clientY : event.clientY) - rect.top

  // x = hue (0-360), y = saturation (100-0)
  sceneColorPicker.value.h = Math.round((x / rect.width) * 360)
  sceneColorPicker.value.s = Math.round(100 - (y / rect.height) * 100)
}

function startSceneColorPick(event) {
  event.preventDefault()
  handleSceneColorPick(event)

  const moveHandler = (e) => {
    e.preventDefault()
    handleSceneColorPick(e)
  }
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

const availableGroupsToAdd = computed(() => {
  if (!groups.value || !Array.isArray(groups.value)) return []
  const usedGroupIds = editGroupValuesForm.value.map(gv => gv.group_id)
  return groups.value.filter(g => !usedGroupIds.includes(g.id))
})

const enabledGroupCount = computed(() => {
  if (!groups.value || !Array.isArray(groups.value)) return 0
  return groups.value.filter(g => g.enabled).length
})

const enabledGroups = computed(() => {
  if (!groups.value || !Array.isArray(groups.value)) return []
  return groups.value.filter(g => g.enabled)
})

function getMasterIndicators(scene) {
  if (!scene.master_values || scene.master_values.length === 0) return ''
  const hasGlobal = scene.master_values.some(m => m.master_type === 'global')
  const universeCount = scene.master_values.filter(m => m.master_type === 'universe').length
  const parts = []
  if (hasGlobal) parts.push('G')
  if (universeCount > 0) parts.push(`U${universeCount}`)
  return parts.join(', ')
}

function getMasterIndicatorsTitle(scene) {
  if (!scene.master_values || scene.master_values.length === 0) return ''
  const hasGlobal = scene.master_values.some(m => m.master_type === 'global')
  const universeCount = scene.master_values.filter(m => m.master_type === 'universe').length
  const parts = []
  if (hasGlobal) parts.push('Global Master')
  if (universeCount > 0) parts.push(`${universeCount} Universe Master${universeCount > 1 ? 's' : ''}`)
  return parts.join(', ')
}

function toggleGroup(groupId) {
  const idx = selectedGroups.value.indexOf(groupId)
  if (idx === -1) {
    selectedGroups.value.push(groupId)
  } else {
    selectedGroups.value.splice(idx, 1)
  }
}

function toggleUpdateGroup(groupId) {
  const idx = updateSelectedGroups.value.indexOf(groupId)
  if (idx === -1) {
    updateSelectedGroups.value.push(groupId)
  } else {
    updateSelectedGroups.value.splice(idx, 1)
  }
}

function addGroupValue() {
  if (!addGroupId.value) return
  editGroupValuesForm.value.push({
    group_id: addGroupId.value,
    master_value: 255
  })
  addGroupId.value = null
}

function removeGroupValue(index) {
  editGroupValuesForm.value.splice(index, 1)
}

// Master values helpers
const hasGlobalMaster = computed(() =>
  editMasterValuesForm.value.some(m => m.master_type === 'global')
)

function hasUniverseMaster(universeId) {
  return editMasterValuesForm.value.some(m => m.master_type === 'universe' && m.universe_id === universeId)
}

function getUniverseMasterLabel(universeId) {
  const u = universes.value.find(u => u.id === universeId)
  return u ? `${u.label} Master` : `Universe ${universeId} Master`
}

function addMasterValue() {
  if (!newMasterType.value) return
  if (newMasterType.value === 'global') {
    editMasterValuesForm.value.push({
      master_type: 'global',
      universe_id: null,
      value: newMasterValue.value || 255
    })
  } else if (newMasterType.value.startsWith('universe_')) {
    const uid = parseInt(newMasterType.value.replace('universe_', ''))
    editMasterValuesForm.value.push({
      master_type: 'universe',
      universe_id: uid,
      value: newMasterValue.value || 255
    })
  }
  newMasterType.value = ''
  newMasterValue.value = 255
}

function removeMasterValue(index) {
  editMasterValuesForm.value.splice(index, 1)
}

// Universe selection helpers
function initUniverseSelection() {
  selectedUniverses.value = universes.value.map(u => u.id)
}

function initGroupSelection() {
  // Select all enabled groups by default
  if (groups.value && Array.isArray(groups.value)) {
    selectedGroups.value = groups.value.filter(g => g.enabled).map(g => g.id)
  } else {
    selectedGroups.value = []
  }
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

async function getDefaultTransitionSettings() {
  try {
    const response = await fetchWithAuth('/api/settings')
    const data = await response.json()
    return {
      type: data.settings?.default_transition_type || 'instant',
      duration: parseInt(data.settings?.default_transition_duration) || 0
    }
  } catch (e) {
    console.error('Failed to load default transition settings:', e)
    return { type: 'instant', duration: 0 }
  }
}

async function openNewSceneModal() {
  if (universes.value.length === 0) {
    await dmxStore.loadUniverses()
  }
  // Always reload groups to ensure fresh data
  await loadGroups()
  initUniverseSelection()
  initGroupSelection()

  // Reset master flags
  includeGlobalMaster.value = false
  includeUniverseMasters.value = false

  // Load default transition settings
  const defaults = await getDefaultTransitionSettings()
  sceneForm.value.transition_type = defaults.type
  sceneForm.value.duration = defaults.duration

  showAddScene.value = true
}

function closeSceneModal() {
  showAddScene.value = false
  editingScene.value = null
  sceneForm.value = { name: '', transition_type: 'instant', duration: 0 }
  initUniverseSelection()
  initGroupSelection()
}

async function saveScene() {
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
      // Create new scene with universe and group filters
      const universeFilter = selectedUniverses.value.length === universes.value.length
        ? null
        : selectedUniverses.value
      const groupFilter = selectedGroups.value.length === enabledGroups.value.length
        ? null
        : selectedGroups.value
      await dmxStore.createScene(
        sceneForm.value.name,
        sceneForm.value.transition_type,
        sceneForm.value.transition_type === 'instant' ? 0 : sceneForm.value.duration,
        universeFilter,
        groupFilter,
        {
          includeGlobalMaster: includeGlobalMaster.value,
          includeUniverseMasters: includeUniverseMasters.value
        }
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

async function updateSceneValues(scene) {
  // Load groups if not already loaded
  if (groups.value.length === 0) {
    await loadGroups()
  }
  updatingScene.value = scene
  initUpdateUniverseSelection(scene)
  initUpdateGroupSelection(scene)
  updateMergeMode.value = 'replace_all'

  // Initialize master flags based on existing scene data
  const hasMasters = scene.master_values && scene.master_values.length > 0
  updateIncludeGlobalMaster.value = hasMasters && scene.master_values.some(m => m.master_type === 'global')
  updateIncludeUniverseMasters.value = hasMasters && scene.master_values.some(m => m.master_type === 'universe')
}

function initUpdateGroupSelection(scene) {
  // Select all enabled groups by default, or groups already in the scene
  const sceneGroupIds = scene.group_values?.map(gv => gv.group_id) || []
  if (sceneGroupIds.length > 0) {
    // Pre-select groups that are in the scene
    updateSelectedGroups.value = sceneGroupIds.filter(gid =>
      enabledGroups.value.some(g => g.id === gid)
    )
  } else {
    // No groups in scene, select all enabled groups
    updateSelectedGroups.value = enabledGroups.value.map(g => g.id)
  }
}

async function confirmUpdateValues() {
  try {
    const universeFilter = updateSelectedUniverses.value.length === universes.value.length
      ? null
      : updateSelectedUniverses.value
    const groupFilter = updateSelectedGroups.value.length === enabledGroups.value.length
      ? null
      : updateSelectedGroups.value
    await dmxStore.updateScene(
      updatingScene.value.id,
      universeFilter,
      updateMergeMode.value,
      groupFilter,
      {
        includeGlobalMaster: updateIncludeGlobalMaster.value,
        includeUniverseMasters: updateIncludeUniverseMasters.value
      }
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
    editGroupValuesForm.value = freshScene.group_values ? freshScene.group_values.map(gv => ({ ...gv })) : []
    editMasterValuesForm.value = freshScene.master_values ? freshScene.master_values.map(mv => ({ ...mv })) : []
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
    // Clamp values to valid DMX range
    const clampedValues = editValuesForm.value.map(v => ({
      ...v,
      value: Math.max(0, Math.min(255, v.value || 0)),
      channel: Math.max(1, Math.min(512, v.channel || 1))
    }))

    // Clamp group master values and preserve color_state
    const clampedGroupValues = editGroupValuesForm.value.map(gv => ({
      group_id: gv.group_id,
      master_value: Math.max(0, Math.min(255, gv.master_value || 0)),
      color_state_h: gv.color_state_h,
      color_state_s: gv.color_state_s,
      color_state_l: gv.color_state_l
    }))

    // Clamp master values
    const clampedMasterValues = editMasterValuesForm.value.map(mv => ({
      master_type: mv.master_type,
      universe_id: mv.universe_id,
      value: Math.max(0, Math.min(255, mv.value || 0))
    }))

    const response = await fetch(`/api/scenes/update/${editingValues.value.id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        ...authStore.getAuthHeaders()
      },
      body: JSON.stringify({
        values: clampedValues,
        group_values: clampedGroupValues,
        master_values: clampedMasterValues
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
/* Drag-and-drop styles */
.scene-row-ghost {
  opacity: 0.4;
  background: var(--bg-secondary);
}

.scene-row-dragging {
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
  touch-action: manipulation;
}

.action-buttons .btn {
  touch-action: manipulation;
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

/* Groups tab styling */
.groups-tab {
  background: rgba(74, 222, 128, 0.1) !important;
  border-color: rgba(74, 222, 128, 0.3) !important;
  order: -1;  /* Always appear FIRST in flex container */
}

.groups-tab.active {
  background: rgba(74, 222, 128, 0.2) !important;
  border-color: var(--indicator-group) !important;
}

/* Group checkbox styling */
.group-checkbox {
  background: rgba(74, 222, 128, 0.1) !important;
  border-color: rgba(74, 222, 128, 0.3) !important;
}

.group-checkbox.selected {
  background: rgba(74, 222, 128, 0.2) !important;
  border-color: var(--indicator-group) !important;
}

.group-checkbox:hover {
  border-color: var(--indicator-group) !important;
}

/* Masters tab styling */
.masters-tab {
  background: rgba(245, 158, 11, 0.1) !important;
  border-color: rgba(245, 158, 11, 0.3) !important;
  order: -1;  /* Appear before universe tabs, after groups */
}

.masters-tab.active {
  background: rgba(245, 158, 11, 0.2) !important;
  border-color: #f59e0b !important;
}

.group-name-cell {
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Group values row styling */
.group-value-row {
  grid-template-columns: 1fr 80px 32px 36px !important;
}

.group-values-header {
  grid-template-columns: 1fr 80px 32px 36px !important;
}

.color-preview-small {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  border: 1px solid var(--border-color);
}

.color-preview-none {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 12px;
}

/* Master checkboxes styling */
.master-checkboxes {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.master-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: rgba(233, 69, 96, 0.1);
  border: 1px solid rgba(233, 69, 96, 0.3);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
  font-size: 13px;
}

.master-checkbox:hover {
  border-color: var(--accent);
}

.master-checkbox.selected {
  background: rgba(233, 69, 96, 0.2);
  border-color: var(--accent);
}

.master-checkbox input[type="checkbox"] {
  accent-color: var(--accent);
}

.help-text {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 8px;
}

/* Master indicators in table */
.master-indicators {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(233, 69, 96, 0.15);
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
}

.no-masters {
  color: var(--text-secondary);
}

/* Mobile responsive */
@media (max-width: 768px) {
  .data-table th:nth-child(4),
  .data-table td:nth-child(4),
  .data-table th:nth-child(5),
  .data-table td:nth-child(5),
  .data-table th:nth-child(7),
  .data-table td:nth-child(7) {
    display: none; /* Hide Duration, Channels, and Masters columns */
  }

  .action-buttons {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .action-buttons .btn {
    width: 100%;
    padding: 4px 8px;
    font-size: 11px;
  }
}

/* Scene Color Picker Modal */
.scene-color-overlay {
  z-index: 1100;
}

.scene-color-picker-modal {
  width: 320px;
  max-width: 90vw;
}

.scene-color-picker-content {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.color-picker-area {
  width: 100%;
  height: 150px;
  border-radius: 8px;
  cursor: crosshair;
  position: relative;
  background: linear-gradient(to bottom, white 0%, transparent 50%, black 100%),
              linear-gradient(to right,
                hsl(0, 100%, 50%),
                hsl(60, 100%, 50%),
                hsl(120, 100%, 50%),
                hsl(180, 100%, 50%),
                hsl(240, 100%, 50%),
                hsl(300, 100%, 50%),
                hsl(360, 100%, 50%)
              );
}

.color-picker-indicator {
  position: absolute;
  width: 16px;
  height: 16px;
  border: 2px solid white;
  border-radius: 50%;
  box-shadow: 0 0 4px rgba(0,0,0,0.5);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

.lightness-slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.lightness-slider {
  flex: 1;
}

.color-preview-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.color-preview-large {
  width: 60px;
  height: 60px;
  border-radius: 8px;
  border: 2px solid var(--border-color);
}

.color-values {
  font-size: 12px;
  color: var(--text-secondary);
}

.color-preview-clickable {
  cursor: pointer;
}

.color-preview-clickable:hover {
  transform: scale(1.1);
  box-shadow: 0 0 4px rgba(255,255,255,0.3);
}

.color-preview-placeholder {
  width: 24px;
  height: 24px;
}
</style>

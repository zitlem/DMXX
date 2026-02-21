<template>
  <div class="control-flow-page">
    <div class="card-header">
      <h2 class="card-title">Control Flow</h2>
      <div class="header-actions">
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
        <button class="btn btn-small btn-secondary" @click="clearSelection" :disabled="!lockedBox">
          Clear Selection
        </button>
        <button class="btn btn-small btn-secondary" @click="refreshData" :disabled="loading">
          {{ loading ? 'Loading...' : 'Refresh' }}
        </button>
      </div>
    </div>

    <!-- Info Banners -->
    <div v-if="!hasAnyExternalInput && !loading" class="info-banner">
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="12" cy="12" r="10"></circle>
        <line x1="12" y1="16" x2="12" y2="12"></line>
        <line x1="12" y1="8" x2="12.01" y2="8"></line>
      </svg>
      <span>
        <strong>No external inputs configured.</strong>
        To receive DMX data from external sources (Art-Net, sACN), go to
        <router-link to="/io">Input/Output</router-link>
        and configure an input on your universe.
      </span>
    </div>

    <!-- Flow Container with SVG overlay -->
    <div class="flow-container" ref="flowContainer">
      <!-- Background lines (passthrough) - underneath GROUPS -->
      <svg class="connection-lines background-lines" :class="{ 'path-active': hoveredBox }">
        <line
          v-for="line in backgroundLines"
          :key="line.id"
          :x1="line.x1"
          :y1="line.y1"
          :x2="line.x2"
          :y2="line.y2"
          :stroke="line.color"
          :stroke-width="highlightedLineIndices.has(line.id) ? 3 : 2"
          :stroke-dasharray="line.isMapped ? '0' : '4,2'"
          :stroke-opacity="hoveredBox ? (highlightedLineIndices.has(line.id) ? 1 : 0.15) : (line.opacity || 0.7)"
          :class="{ highlighted: highlightedLineIndices.has(line.id) }"
        />
      </svg>
      <!-- Foreground lines (group-related) - on top of GROUPS -->
      <svg class="connection-lines foreground-lines" :class="{ 'path-active': hoveredBox }">
        <line
          v-for="line in foregroundLines"
          :key="line.id"
          :x1="line.x1"
          :y1="line.y1"
          :x2="line.x2"
          :y2="line.y2"
          :stroke="line.color"
          :stroke-width="highlightedLineIndices.has(line.id) ? 3 : 2"
          :stroke-dasharray="line.isMapped ? '0' : '4,2'"
          :stroke-opacity="hoveredBox ? (highlightedLineIndices.has(line.id) ? 1 : 0.15) : (line.opacity || 0.7)"
          :class="{ highlighted: highlightedLineIndices.has(line.id) }"
        />
      </svg>

      <!-- Flow Columns -->
      <div class="flow-columns">
      <!-- INPUT Column -->
      <div class="flow-column">
        <div class="column-header">INPUT</div>
        <div class="column-content no-flex">
          <div
            v-for="(universe, idx) in inputUniverses"
            :key="'input-' + universe.id"
            class="universe-section vertical"
          >
            <div class="universe-label-vertical" :style="{ background: getUniverseColor(idx) }">
              <span
                v-for="n in getLabelRepeatCount(universe.channels.length)"
                :key="n"
                class="label-repeat"
              >{{ universe.label }}</span>
            </div>
            <div class="channel-column">
              <div
                v-for="ch in universe.channels"
                :key="ch"
                class="channel-box"
                :ref="el => setChannelRef('input', universe.id, ch, el)"
                :style="{ '--universe-color': getUniverseColor(idx) }"
                :title="`${universe.label} Ch ${ch}`"
                :class="{ highlighted: isBoxHighlighted('input', universe.id, ch), dimmed: hoveredBox && !isBoxHighlighted('input', universe.id, ch), locked: lockedBox && lockedBox.column === 'input' && lockedBox.universeId === universe.id && lockedBox.channel === ch }"
                @mouseenter="onBoxHover('input', universe.id, ch)"
                @mouseleave="onBoxLeave"
                @click="onBoxClick('input', universe.id, ch)"
              >
                <span class="channel-name">{{ ch }}</span>
                <span class="dmx-value">{{ formatValue(getInputValue(universe.id, ch)) }}</span>
              </div>
            </div>
          </div>
          <div v-if="inputUniverses.length === 0" class="empty-section">
            No active inputs
          </div>
        </div>
      </div>

      <!-- Arrow -->
      <div class="flow-arrow"></div>

      <!-- MAPPING Column -->
      <div class="flow-column">
        <div class="column-header">MAPPING</div>
        <div class="column-content">
          <!-- Show channels flowing through (passthrough + mapped) -->
          <div v-if="mappingUniverses.length > 0">
            <div
              v-for="universe in mappingUniverses"
              :key="'mapping-' + universe.id"
              class="universe-section vertical"
            >
              <div class="universe-label-vertical" style="background: #a855f7;">
                <span
                  v-for="n in getLabelRepeatCount(universe.allChannels.length)"
                  :key="n"
                  class="label-repeat"
                >{{ mappingConfig.name }}</span>
              </div>
              <div class="channel-column">
                <div
                  v-for="ch in universe.allChannels"
                  :key="ch"
                  class="channel-box"
                  :ref="el => setChannelRef('mapping', universe.id, ch, el)"
                  :class="{
                    'passthrough': universe.passthroughChannels.includes(ch) && !universe.mappedChannels.includes(ch),
                    'mapped': universe.mappedChannels.includes(ch),
                    'highlighted': isBoxHighlighted('mapping', universe.id, ch),
                    'dimmed': hoveredBox && !isBoxHighlighted('mapping', universe.id, ch),
                    'locked': lockedBox && lockedBox.column === 'mapping' && lockedBox.universeId === universe.id && lockedBox.channel === ch
                  }"
                  :style="{ '--universe-color': getUniverseColorById(universe.id) }"
                  :title="`${universe.label} Ch ${ch}${universe.mappedChannels.includes(ch) ? ' (mapped)' : ' (passthrough)'}`"
                  @mouseenter="onBoxHover('mapping', universe.id, ch)"
                  @mouseleave="onBoxLeave"
                  @click="onBoxClick('mapping', universe.id, ch)"
                >
                  <span class="channel-name">{{ ch }}</span>
                  <span class="dmx-value">{{ formatValue(getInputValue(universe.id, ch)) }}</span>
                </div>
              </div>
            </div>
          </div>

          <div v-else class="empty-section">
            No passthrough or mapping configured
          </div>
        </div>
      </div>

      <!-- Arrow -->
      <div class="flow-arrow"></div>

      <!-- FADERS Column -->
      <div class="flow-column">
        <div class="column-header">FADERS</div>
        <div class="column-content vertical-stack">
          <div
            v-for="(universe, idx) in faderUniverses"
            :key="'fader-' + universe.id"
            class="universe-section vertical"
          >
            <div class="universe-label-vertical" :style="{ background: getUniverseColor(idx) }">
              <span
                v-for="n in getLabelRepeatCount(universe.faders.length)"
                :key="n"
                class="label-repeat"
              >{{ universe.label }}</span>
            </div>
            <div class="channel-column">
              <div
                v-for="fader in universe.faders"
                :key="fader.channel"
                class="fader-box"
                :ref="el => setChannelRef('fader', universe.id, fader.channel, el)"
                :style="{ '--universe-color': getUniverseColor(idx) }"
                :title="`${universe.label} Ch ${fader.channel}`"
                :class="{ highlighted: isBoxHighlighted('fader', universe.id, fader.channel), dimmed: hoveredBox && !isBoxHighlighted('fader', universe.id, fader.channel), locked: lockedBox && lockedBox.column === 'fader' && lockedBox.universeId === universe.id && lockedBox.channel === fader.channel }"
                @mouseenter="onBoxHover('fader', universe.id, fader.channel)"
                @mouseleave="onBoxLeave"
                @click="onBoxClick('fader', universe.id, fader.channel)"
              >
                <span class="channel-name">{{ fader.name }}</span>
                <span v-if="shouldShowFaderValue(universe.id, fader.channel)" class="dmx-value">{{ formatValue(getFader1Value(universe.id, fader.channel)) }}</span>
              </div>
            </div>
          </div>
          <div v-if="faderUniverses.length === 0" class="empty-section">
            No mapped channels
          </div>
        </div>
      </div>

      <!-- Arrow -->
      <div class="flow-arrow"></div>

      <!-- GROUPS Column -->
      <div class="flow-column groups-column">
        <div class="column-header">GROUPS</div>
        <div class="column-content no-flex">
          <div
            v-for="grid in activeGridsWithGroups"
            :key="'grid-' + grid.id"
            class="universe-section vertical"
          >
            <!-- Grid label (similar to universe label) -->
            <div
              class="universe-label-vertical"
              :style="{ background: grid.color || 'var(--accent)' }"
            >
              <span
                v-for="n in getGridLabelRepeatCount(grid.groups.length)"
                :key="n"
                class="label-repeat"
              >{{ grid.name }}</span>
            </div>
            <!-- Groups within this grid -->
            <div class="channel-column">
              <div
                v-for="group in getSortedGridGroups(grid.groups)"
                :key="'group-' + group.id"
                class="group-section"
              >
                <div
                  class="group-label"
                  :ref="el => setChannelRef('group', group.id, 0, el)"
                  :style="{
                    background: group.color || '#6b7280',
                    color: shouldUseDarkText(group.color) ? '#1a1a2e' : 'white'
                  }"
                  :class="{ highlighted: isBoxHighlighted('group', group.id, 0), dimmed: hoveredBox && !isBoxHighlighted('group', group.id, 0), locked: lockedBox && lockedBox.column === 'group' && lockedBox.universeId === group.id && lockedBox.channel === 0 }"
                  @mouseenter="onBoxHover('group', group.id, 0)"
                  @mouseleave="onBoxLeave"
                  @click="onBoxClick('group', group.id, 0)"
                >
                  <span class="channel-name">{{ group.name }}</span>
                  <span class="dmx-value">{{ formatValue(getGroupMasterValue(group)) }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="activeGridsWithGroups.length === 0" class="empty-section">
            No groups configured
          </div>
        </div>
      </div>

      <!-- Arrow -->
      <div class="flow-arrow"></div>

      <!-- OUTPUT Column (with inline masters) -->
      <div class="flow-column output-column">
        <div class="column-header">OUTPUT</div>
        <div class="column-content vertical-stack">
          <div
            v-for="(universe, idx) in faderUniverses"
            :key="'output-' + universe.id"
            class="universe-section vertical"
          >
            <div class="universe-label-vertical" :style="{ background: getUniverseColor(idx) }">
              <span
                v-for="n in getLabelRepeatCount(universe.faders.length)"
                :key="n"
                class="label-repeat"
              >{{ universe.label }}</span>
            </div>
            <div class="channel-column">
              <div
                v-for="(fader, faderIdx) in universe.faders"
                :key="fader.channel"
                class="output-row"
              >
                <!-- Channel Value (raw, before master scaling) -->
                <div
                  class="fader-box"
                  :ref="el => setChannelRef('fader2', universe.id, fader.channel, el)"
                  :style="{
                    '--universe-color': getUniverseColor(idx),
                    backgroundColor: getChannelColor(universe.id, fader.channel),
                    color: shouldUseDarkText(getChannelColor(universe.id, fader.channel)) ? '#1a1a2e' : undefined
                  }"
                  :title="`${universe.label} Ch ${fader.channel}`"
                  :class="{ highlighted: isBoxHighlighted('fader2', universe.id, fader.channel), dimmed: hoveredBox && !isBoxHighlighted('fader2', universe.id, fader.channel), locked: lockedBox && lockedBox.column === 'fader2' && lockedBox.universeId === universe.id && lockedBox.channel === fader.channel }"
                  @mouseenter="onBoxHover('fader2', universe.id, fader.channel)"
                  @mouseleave="onBoxLeave"
                  @click="onBoxClick('fader2', universe.id, fader.channel)"
                >
                  <span class="channel-name">{{ fader.name }}</span>
                  <span class="dmx-value">{{ formatValue(getRawChannelValue(universe.id, fader.channel)) }}</span>
                  <div
                    v-if="getChannelGroupColor(universe.id, fader.channel)"
                    class="fader-group-stripe-vertical"
                    :class="{
                      'connects-top': hasSameGroupColorAbove(universe.id, universe.faders, faderIdx),
                      'connects-bottom': hasSameGroupColorBelow(universe.id, universe.faders, faderIdx)
                    }"
                    :style="{ backgroundColor: getChannelGroupColor(universe.id, fader.channel) }"
                  ></div>
                </div>
                <!-- Universe Master -->
                <div
                  class="master-box-inline universe-master"
                  :style="{ borderColor: getUniverseColor(idx) }"
                  :class="{ highlighted: isBoxHighlighted('fader2', universe.id, fader.channel), dimmed: hoveredBox && !isBoxHighlighted('fader2', universe.id, fader.channel), locked: lockedBox && lockedBox.column === 'fader2' && lockedBox.universeId === universe.id && lockedBox.channel === fader.channel }"
                  @mouseenter="onBoxHover('fader2', universe.id, fader.channel)"
                  @mouseleave="onBoxLeave"
                  @click="onBoxClick('fader2', universe.id, fader.channel)"
                >
                  <span class="channel-name">× U{{ universe.id }}</span>
                  <span class="dmx-value">{{ formatValue(getUniverseGrandmaster(universe.id)) }}</span>
                </div>
                <!-- Global Master -->
                <div
                  class="master-box-inline global-master"
                  :class="{ highlighted: isBoxHighlighted('fader2', universe.id, fader.channel), dimmed: hoveredBox && !isBoxHighlighted('fader2', universe.id, fader.channel), locked: lockedBox && lockedBox.column === 'fader2' && lockedBox.universeId === universe.id && lockedBox.channel === fader.channel }"
                  @mouseenter="onBoxHover('fader2', universe.id, fader.channel)"
                  @mouseleave="onBoxLeave"
                  @click="onBoxClick('fader2', universe.id, fader.channel)"
                >
                  <span class="channel-name">× GM</span>
                  <span class="dmx-value">{{ formatValue(globalGrandmaster) }}</span>
                </div>
                <!-- Final Output -->
                <div
                  class="output-box"
                  :class="{ highlighted: isBoxHighlighted('fader2', universe.id, fader.channel), dimmed: hoveredBox && !isBoxHighlighted('fader2', universe.id, fader.channel), locked: lockedBox && lockedBox.column === 'fader2' && lockedBox.universeId === universe.id && lockedBox.channel === fader.channel }"
                  @mouseenter="onBoxHover('fader2', universe.id, fader.channel)"
                  @mouseleave="onBoxLeave"
                  @click="onBoxClick('fader2', universe.id, fader.channel)"
                >
                  <span class="channel-name">= Out</span>
                  <span class="dmx-value">{{ formatValue(outputValues[universe.id]?.[fader.channel - 1] || 0) }}</span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="faderUniverses.length === 0" class="empty-section">
            No mapped channels
          </div>
        </div>
      </div>

    </div>
    </div>

    <!-- Inactivity Overlay -->
    <div v-if="pollingPaused" class="polling-paused-overlay">
      <div class="paused-content">
        <p>Updates paused due to inactivity</p>
        <button class="btn btn-primary" @click="resumePolling">Continue</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useDmxStore } from '../stores/dmx.js'
import { wsManager } from '../websocket.js'

const authStore = useAuthStore()
const dmxStore = useDmxStore()

// Check if any channels are parked
const hasParkedChannels = computed(() => {
  return Object.keys(dmxStore.parkedChannels).some(uid =>
    Object.keys(dmxStore.parkedChannels[uid] || {}).length > 0
  )
})

async function toggleBypass() {
  await dmxStore.toggleInputBypass()
}

// Universe color palette
const universeColors = [
  '#3b82f6', // blue
  '#22c55e', // green
  '#f59e0b', // amber
  '#ef4444', // red
  '#8b5cf6', // violet
  '#06b6d4', // cyan
  '#ec4899', // pink
  '#84cc16', // lime
]

// Data
const ioConfig = ref({ universes: [] })
const mappingData = ref({ mappings: [], status: { enabled: false } })
const gridsData = ref([])  // Grids containing groups
const loading = ref(false)

// DMX values
const inputValues = ref({})   // { universeId: [512 values] }
const outputValues = ref({})  // { universeId: [512 values] }
const groupValues = ref({})   // { groupId: value }
const outputPollInterval = ref(null)  // Polling interval for output values
const pollingPaused = ref(false)
const inactivityTimeout = ref(null)
const INACTIVITY_TIMEOUT_MS = 60000  // 1 minute

// Grandmaster state
const globalGrandmaster = ref(255)
const universeGrandmasters = ref({})  // { universeId: value }

// Refs for connection lines
const flowContainer = ref(null)
const channelRefs = ref({})
const renderedLines = ref([])

// Hover path highlighting state
const hoveredBox = ref(null)  // { column, universeId, channel }
const lockedBox = ref(null)   // Clicked/locked selection
const highlightedBoxes = ref(new Set())
const highlightedLineIndices = ref(new Set())

// Computed: Split lines into background (passthrough) and foreground (group-related)
const backgroundLines = computed(() => renderedLines.value.filter(line => line.background))
const foregroundLines = computed(() => renderedLines.value.filter(line => !line.background))

// Set channel ref for position tracking
function setChannelRef(column, universeId, channel, el) {
  const key = `${column}-${universeId}-${channel}`
  if (el) {
    channelRefs.value[key] = el
  } else {
    delete channelRefs.value[key]
  }
}

// Hover path highlighting functions
function onBoxHover(column, universeId, channel) {
  if (lockedBox.value) return  // Don't change highlight if locked
  hoveredBox.value = { column, universeId, channel }
  const path = traceFullPath(column, universeId, channel)
  highlightedBoxes.value = path.boxes
  highlightedLineIndices.value = path.lines
}

function onBoxLeave() {
  if (lockedBox.value) return  // Don't clear if locked
  hoveredBox.value = null
  highlightedBoxes.value = new Set()
  highlightedLineIndices.value = new Set()
}

function onBoxClick(column, universeId, channel) {
  const boxKey = `${column}-${universeId}-${channel}`

  // If there's a lock and clicking on a highlighted box, toggle off
  if (lockedBox.value && highlightedBoxes.value.has(boxKey)) {
    lockedBox.value = null
    hoveredBox.value = null
    highlightedBoxes.value = new Set()
    highlightedLineIndices.value = new Set()
  } else {
    // Lock this new selection
    lockedBox.value = { column, universeId, channel }
    hoveredBox.value = { column, universeId, channel }
    const path = traceFullPath(column, universeId, channel)
    highlightedBoxes.value = path.boxes
    highlightedLineIndices.value = path.lines
  }
}

function clearSelection() {
  lockedBox.value = null
  hoveredBox.value = null
  highlightedBoxes.value = new Set()
  highlightedLineIndices.value = new Set()
}

function traceFullPath(column, universeId, channel) {
  const boxes = new Set()
  const lines = new Set()
  const boxKey = `${column}-${universeId}-${channel}`
  boxes.add(boxKey)

  // Trace forward (downstream)
  traceForward(column, universeId, channel, boxes, lines, new Set())
  // Trace backward (upstream)
  traceBackward(column, universeId, channel, boxes, lines, new Set())

  return { boxes, lines }
}

function traceForward(column, universeId, channel, boxes, lines, visited) {
  const key = `${column}-${universeId}-${channel}`
  if (visited.has(key)) return
  visited.add(key)

  // Based on column, determine next connections
  if (column === 'input') {
    // INPUT → MAPPING (same channel passthrough)
    const mappingKey = `mapping-${universeId}-${channel}`
    if (channelRefs.value[mappingKey]) {
      boxes.add(mappingKey)
      // Find the line index
      findLineIndex('input', universeId, channel, 'mapping', universeId, channel, lines)
      traceForward('mapping', universeId, channel, boxes, lines, visited)
    }
  } else if (column === 'mapping') {
    // MAPPING → FADERS (could be mapped or passthrough)
    const isPassthroughBehavior = !mappingConfig.value.enabled || mappingConfig.value.unmappedBehavior === 'Passthrough'

    // Check for explicit mappings
    if (mappingConfig.value.enabled) {
      const mappings = mappingConfig.value.mappings.filter(
        m => m.src_universe === universeId && m.src_channel === channel
      )
      mappings.forEach(mapping => {
        const dstUniverse = mapping.dst_universe || universeId
        const dstChannel = mapping.dst_channel
        const faderKey = `fader-${dstUniverse}-${dstChannel}`
        if (channelRefs.value[faderKey]) {
          boxes.add(faderKey)
          findLineIndex('mapping', universeId, channel, 'fader', dstUniverse, dstChannel, lines)
          traceForward('fader', dstUniverse, dstChannel, boxes, lines, visited)
        }
      })
    }

    // Passthrough
    if (isPassthroughBehavior) {
      const faderKey = `fader-${universeId}-${channel}`
      if (channelRefs.value[faderKey]) {
        boxes.add(faderKey)
        findLineIndex('mapping', universeId, channel, 'fader', universeId, channel, lines)
        traceForward('fader', universeId, channel, boxes, lines, visited)
      }
    }
  } else if (column === 'fader') {
    // FADERS → GROUPS (if this fader is a group master)
    activeGroups.value.forEach(group => {
      if (group.masterUniverse === universeId && group.masterChannel === channel) {
        const groupKey = `group-${group.id}-0`
        if (channelRefs.value[groupKey]) {
          boxes.add(groupKey)
          findLineIndex('fader', universeId, channel, 'group', group.id, 0, lines)
          traceForward('group', group.id, 0, boxes, lines, visited)
        }
      }
    })

    // FADERS → FADERS2 (direct connection)
    const fader2Key = `fader2-${universeId}-${channel}`
    if (channelRefs.value[fader2Key]) {
      boxes.add(fader2Key)
      findLineIndex('fader', universeId, channel, 'fader2', universeId, channel, lines)
    }
  } else if (column === 'group') {
    // GROUPS → FADERS2 (group to member faders)
    const group = activeGroups.value.find(g => g.id === universeId)
    if (group) {
      group.members.forEach(member => {
        const fader2Key = `fader2-${member.universe_id}-${member.channel}`
        if (channelRefs.value[fader2Key]) {
          boxes.add(fader2Key)
          findLineIndex('group', universeId, 0, 'fader2', member.universe_id, member.channel, lines)
        }
      })
    }
  }
}

function traceBackward(column, universeId, channel, boxes, lines, visited) {
  const key = `${column}-${universeId}-${channel}`
  if (visited.has(key)) return
  visited.add(key)

  if (column === 'fader2') {
    // FADERS2 ← GROUPS (if this fader is a group member)
    activeGroups.value.forEach(group => {
      const isMember = group.members.some(m => m.universe_id === universeId && m.channel === channel)
      if (isMember) {
        const groupKey = `group-${group.id}-0`
        if (channelRefs.value[groupKey]) {
          boxes.add(groupKey)
          findLineIndex('group', group.id, 0, 'fader2', universeId, channel, lines)
          traceBackward('group', group.id, 0, boxes, lines, visited)
        }
      }
    })

    // FADERS2 ← FADERS
    const faderKey = `fader-${universeId}-${channel}`
    if (channelRefs.value[faderKey]) {
      boxes.add(faderKey)
      findLineIndex('fader', universeId, channel, 'fader2', universeId, channel, lines)
      traceBackward('fader', universeId, channel, boxes, lines, visited)
    }
  } else if (column === 'group') {
    // GROUPS ← FADERS (find master fader)
    const group = activeGroups.value.find(g => g.id === universeId)
    if (group && group.masterUniverse && group.masterChannel) {
      const faderKey = `fader-${group.masterUniverse}-${group.masterChannel}`
      if (channelRefs.value[faderKey]) {
        boxes.add(faderKey)
        findLineIndex('fader', group.masterUniverse, group.masterChannel, 'group', universeId, 0, lines)
        traceBackward('fader', group.masterUniverse, group.masterChannel, boxes, lines, visited)
      }
    }
  } else if (column === 'fader') {
    // FADERS ← MAPPING
    const isPassthroughBehavior = !mappingConfig.value.enabled || mappingConfig.value.unmappedBehavior === 'Passthrough'

    // Check for explicit mappings (reverse lookup)
    if (mappingConfig.value.enabled) {
      const mappings = mappingConfig.value.mappings.filter(
        m => (m.dst_universe || m.src_universe) === universeId && m.dst_channel === channel
      )
      mappings.forEach(mapping => {
        const mappingKey = `mapping-${mapping.src_universe}-${mapping.src_channel}`
        if (channelRefs.value[mappingKey]) {
          boxes.add(mappingKey)
          findLineIndex('mapping', mapping.src_universe, mapping.src_channel, 'fader', universeId, channel, lines)
          traceBackward('mapping', mapping.src_universe, mapping.src_channel, boxes, lines, visited)
        }
      })
    }

    // Passthrough (same channel)
    if (isPassthroughBehavior) {
      const mappingKey = `mapping-${universeId}-${channel}`
      if (channelRefs.value[mappingKey]) {
        boxes.add(mappingKey)
        findLineIndex('mapping', universeId, channel, 'fader', universeId, channel, lines)
        traceBackward('mapping', universeId, channel, boxes, lines, visited)
      }
    }
  } else if (column === 'mapping') {
    // MAPPING ← INPUT
    const inputKey = `input-${universeId}-${channel}`
    if (channelRefs.value[inputKey]) {
      boxes.add(inputKey)
      findLineIndex('input', universeId, channel, 'mapping', universeId, channel, lines)
    }
  }
}

function findLineIndex(srcCol, srcUniv, srcCh, dstCol, dstUniv, dstCh, lineSet) {
  // Generate the same ID pattern used when creating lines
  let lineId
  if (srcCol === 'input' && dstCol === 'mapping') {
    lineId = `input-mapping-${srcUniv}-${srcCh}`
  } else if (srcCol === 'mapping' && dstCol === 'fader') {
    lineId = `mapping-fader-${srcUniv}-${srcCh}-${dstUniv}-${dstCh}`
  } else if (srcCol === 'fader' && dstCol === 'group') {
    lineId = `fader-group-${srcUniv}-${srcCh}-${dstUniv}`
  } else if (srcCol === 'group' && dstCol === 'fader2') {
    lineId = `group-fader2-${srcUniv}-${dstUniv}-${dstCh}`
  } else if (srcCol === 'fader' && dstCol === 'fader2') {
    lineId = `fader-fader2-${srcUniv}-${srcCh}`
  }
  if (lineId) {
    lineSet.add(lineId)
  }
}

function isBoxHighlighted(column, universeId, channel) {
  return highlightedBoxes.value.has(`${column}-${universeId}-${channel}`)
}

// Helper to fetch with auth
async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

// Get universe color by index
function getUniverseColor(idx) {
  return universeColors[idx % universeColors.length]
}

// Get universe color by ID
function getUniverseColorById(universeId) {
  const idx = ioConfig.value.universes.findIndex(u => u.id === universeId)
  return idx >= 0 ? getUniverseColor(idx) : '#6b7280'
}

function getChannelColor(universeId, channel) {
  return dmxStore.getChannelColor(universeId, channel)
}

function getChannelGroupColor(universeId, channel) {
  return dmxStore.getChannelGroupColor(universeId, channel)
}

function hasSameGroupColorAbove(universeId, faders, index) {
  if (index === 0) return false
  const currentColor = dmxStore.getChannelGroupColor(universeId, faders[index].channel)
  const aboveColor = dmxStore.getChannelGroupColor(universeId, faders[index - 1].channel)
  return currentColor && aboveColor && currentColor === aboveColor
}

function hasSameGroupColorBelow(universeId, faders, index) {
  if (index === faders.length - 1) return false
  const currentColor = dmxStore.getChannelGroupColor(universeId, faders[index].channel)
  const belowColor = dmxStore.getChannelGroupColor(universeId, faders[index + 1].channel)
  return currentColor && belowColor && currentColor === belowColor
}

// DMX value helpers
function getInputValue(universeId, channel) {
  return inputValues.value[universeId]?.[channel - 1] || 0
}

function getOutputValue(universeId, channel) {
  return outputValues.value[universeId]?.[channel - 1] || 0
}

function getUniverseGrandmaster(universeId) {
  return universeGrandmasters.value[universeId] ?? 255
}

function getRawChannelValue(universeId, channel) {
  // Reverse-calculate raw value from scaled output
  const scaledValue = outputValues.value[universeId]?.[channel - 1] || 0
  const universeGM = getUniverseGrandmaster(universeId)
  const globalGM = globalGrandmaster.value

  // Reverse the scaling: raw = scaled / (universe_gm/255) / (global_gm/255)
  if (universeGM === 0 || globalGM === 0) return 0
  const raw = Math.round(scaledValue / (universeGM / 255) / (globalGM / 255))
  return Math.min(255, raw)
}

function formatValue(value) {
  const percent = Math.round(value / 255 * 100)
  return `${value}|${percent}%`
}

// Get the appropriate DMX value for FADERS1 display
function getFader1Value(universeId, channel) {
  // Check if this is an explicit mapping destination
  if (mappingConfig.value.enabled) {
    const mapping = mappingConfig.value.mappings.find(
      m => (m.dst_universe || m.src_universe) === universeId && m.dst_channel === channel
    )
    if (mapping) {
      // Use input value from source channel
      return getInputValue(mapping.src_universe, mapping.src_channel)
    }
  }

  // Check if this is a passthrough channel
  const inputUniverse = inputUniverses.value.find(u => u.id === universeId)
  const isPassthrough = inputUniverse?.isPassthrough &&
    channel >= inputUniverse.channelStart &&
    channel <= inputUniverse.channelEnd

  if (isPassthrough) {
    return getInputValue(universeId, channel)
  }
  return getOutputValue(universeId, channel)
}

// Get the DMX value for FADERS2 display - uses computed for reactivity
function getFader2Value(universeId, channel) {
  return fader2Values.value[universeId]?.[channel - 1] || 0
}

// Check if channel is connected to a group (master or member)
function isGroupChannel(universeId, channel) {
  return activeGroups.value.some(group => {
    // Check if this is the master channel
    if (group.masterUniverse === universeId && group.masterChannel === channel) {
      return true
    }
    // Check if this is a member channel
    return group.members.some(m => m.universe_id === universeId && m.channel === channel)
  })
}

// Check if channel should show DMX value in FADERS1
function shouldShowFaderValue(universeId, channel) {
  // Check if this channel is within a passthrough input range
  const inputUniverse = inputUniverses.value.find(u => u.id === universeId)
  const isInPassthroughRange = inputUniverse?.isPassthrough &&
    channel >= inputUniverse.channelStart &&
    channel <= inputUniverse.channelEnd

  // If mapping is disabled, show values for passthrough channels
  if (!mappingConfig.value.enabled) {
    return isInPassthroughRange
  }

  // If mapping is enabled, check for explicit mapping to this channel
  const isExplicitlyMapped = mappingConfig.value.mappings.some(
    m => (m.dst_universe || m.src_universe) === universeId && m.dst_channel === channel
  )
  if (isExplicitlyMapped) return true

  // If unmapped behavior is passthrough, show values for 1:1 passthrough channels
  if (mappingConfig.value.unmappedBehavior === 'Passthrough' && isInPassthroughRange) {
    // Check this channel isn't a source that got remapped elsewhere
    const isRemappedSource = mappingConfig.value.mappings.some(
      m => m.src_universe === universeId && m.src_channel === channel
    )
    return !isRemappedSource
  }

  return false
}

// Get group master value - uses reactive groupValues for real-time updates
function getGroupMasterValue(group) {
  // Use reactive groupValues for real-time updates
  if (groupValues.value[group.id] !== undefined) {
    return groupValues.value[group.id]
  }
  // Fallback to stored master_value (search across all grids)
  for (const grid of gridsData.value) {
    const originalGroup = (grid.groups || []).find(g => g.id === group.id)
    if (originalGroup && originalGroup.master_value !== undefined) {
      return originalGroup.master_value
    }
  }
  return 0
}

// Get fader name for a channel
function getFaderName(universeId, channel) {
  // Look up fader in faderUniverses
  const universe = faderUniverses.value.find(u => u.id === universeId)
  if (universe) {
    const fader = universe.faders.find(f => f.channel === channel)
    if (fader) {
      return fader.name
    }
  }
  return `Ch ${channel}`
}

// Generate channel array
function generateChannels(start, end) {
  const channels = []
  for (let i = start; i <= end; i++) {
    channels.push(i)
  }
  return channels
}

// Computed: Input universes with their channels
const inputUniverses = computed(() => {
  return ioConfig.value.universes
    .filter(u => u.input && u.input.input_type !== 'none' && u.input.enabled)
    .map(u => {
      const channelStart = u.input.channel_start || 1
      const channelEnd = u.input.channel_end || 512
      // Get passthrough mode
      const passthroughMode = u.passthrough?.passthrough_mode || 'off'
      const isPassthrough = passthroughMode === 'faders_output' || passthroughMode === 'output_only'
      return {
        id: u.id,
        label: u.label,
        inputType: formatInputType(u.input.input_type),
        channelStart,
        channelEnd,
        // Show ALL channels in the configured input range
        channels: generateChannels(channelStart, channelEnd),
        passthroughMode,
        isPassthrough
      }
    })
})

// Computed: Has any external input
const hasAnyExternalInput = computed(() => {
  return inputUniverses.value.length > 0
})

// Computed: Mapping config
const mappingConfig = computed(() => {
  const activeMapping = mappingData.value.mappings?.find(m => m.enabled)
  if (activeMapping) {
    return {
      enabled: true,
      name: activeMapping.name,
      mappings: activeMapping.mappings || [],
      unmappedBehavior: activeMapping.unmapped_behavior === 'passthrough' ? 'Passthrough' : 'Ignore'
    }
  }
  return { enabled: false, name: '', mappings: [], unmappedBehavior: 'Passthrough' }
})

// Computed: Channels flowing through mapping (passthrough + explicitly mapped)
const mappingUniverses = computed(() => {
  const universeMap = {}

  // Add passthrough channels from input universes
  inputUniverses.value.forEach(input => {
    if (input.isPassthrough) {
      if (!universeMap[input.id]) {
        universeMap[input.id] = {
          id: input.id,
          label: input.label,
          passthroughChannels: [],
          mappedChannels: []
        }
      }
      universeMap[input.id].passthroughChannels = input.channels
    }
  })

  // Add explicitly mapped channels
  if (mappingConfig.value.enabled) {
    mappingConfig.value.mappings.forEach(m => {
      const key = m.src_universe
      if (!universeMap[key]) {
        const universe = ioConfig.value.universes.find(u => u.id === key)
        universeMap[key] = {
          id: key,
          label: universe?.label || `Universe ${key}`,
          passthroughChannels: [],
          mappedChannels: []
        }
      }
      if (!universeMap[key].mappedChannels.includes(m.src_channel)) {
        universeMap[key].mappedChannels.push(m.src_channel)
      }
    })
  }

  return Object.values(universeMap).map(u => ({
    ...u,
    mappedChannels: u.mappedChannels.sort((a, b) => a - b),
    // Combine for display
    allChannels: [...new Set([...u.passthroughChannels, ...u.mappedChannels])].sort((a, b) => a - b)
  }))
})

// Computed: Grids with their active (enabled) groups
const activeGridsWithGroups = computed(() => {
  return gridsData.value
    .map(grid => ({
      ...grid,
      groups: (grid.groups || []).filter(g => g.enabled).map(g => ({
        id: g.id,
        name: g.name,
        mode: g.mode,
        enabled: g.enabled,
        color: g.color,
        members: g.members || [],
        masterUniverse: g.master_universe,
        masterChannel: g.master_channel
      }))
    }))
    .filter(grid => grid.groups.length > 0)
})

// Computed: Active groups (flat list for compatibility with existing code)
const activeGroups = computed(() => {
  return activeGridsWithGroups.value.flatMap(grid => grid.groups)
})

// Helper: Sort groups within a grid by anchor channel
function getSortedGridGroups(groups) {
  return [...groups].sort((a, b) => {
    const aAnchor = a.masterChannel || (a.members[0]?.channel ?? Infinity)
    const bAnchor = b.masterChannel || (b.members[0]?.channel ?? Infinity)
    return aAnchor - bAnchor
  })
}

// Helper: Calculate label repeat count for grid labels
function getGridLabelRepeatCount(groupCount) {
  // Each group label is ~40px tall, repeat grid name accordingly
  const labelHeight = 40
  const totalHeight = groupCount * labelHeight
  return Math.max(1, Math.floor(totalHeight / 60))
}

// Computed: Groups sorted by connected fader position to minimize line crossovers
const sortedGroups = computed(() => {
  return activeGridsWithGroups.value.flatMap(grid => getSortedGridGroups(grid.groups))
})

// Calculate how many times to repeat a label based on channel count
function getLabelRepeatCount(channelCount, interval = 8) {
  return Math.max(1, Math.ceil(channelCount / interval))
}

// Determine if text should be dark based on background color luminance
function shouldUseDarkText(hexColor) {
  if (!hexColor) return false
  const hex = hexColor.replace('#', '')
  const r = parseInt(hex.substr(0, 2), 16)
  const g = parseInt(hex.substr(2, 2), 16)
  const b = parseInt(hex.substr(4, 2), 16)
  // Calculate relative luminance
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.5
}

// Computed: Fader universes (destination channels from mapping config)
const faderUniverses = computed(() => {
  const universeMap = {}

  // Get destination channels from active mapping
  if (mappingConfig.value.enabled) {
    mappingConfig.value.mappings.forEach(m => {
      // Skip virtual targets (global_master, universe_master) - they don't have dst_universe
      if (m.dst_target_type && m.dst_target_type !== 'channel') return

      const universeId = m.dst_universe || m.src_universe
      if (universeId === null || universeId === undefined) return

      if (!universeMap[universeId]) {
        const universe = ioConfig.value.universes.find(u => u.id === universeId)
        universeMap[universeId] = {
          id: universeId,
          label: universe?.label || `Universe ${universeId}`,
          faders: []
        }
      }
      // Add destination channel as a fader
      const existingFader = universeMap[universeId].faders.find(f => f.channel === m.dst_channel)
      if (!existingFader && m.dst_channel) {
        universeMap[universeId].faders.push({
          channel: m.dst_channel,
          name: `Ch ${m.dst_channel}`
        })
      }
    })
  }

  // Also add passthrough channels if passthrough is enabled
  inputUniverses.value.forEach(input => {
    if (input.isPassthrough) {
      if (!universeMap[input.id]) {
        universeMap[input.id] = {
          id: input.id,
          label: input.label,
          faders: []
        }
      }
      input.channels.forEach(ch => {
        const existingFader = universeMap[input.id].faders.find(f => f.channel === ch)
        if (!existingFader) {
          universeMap[input.id].faders.push({
            channel: ch,
            name: `Ch ${ch}`
          })
        }
      })
    }
  })

  // Also add group member channels
  activeGroups.value.forEach(group => {
    group.members.forEach(member => {
      // Skip virtual targets (global_master, universe_master)
      if (member.target_type && member.target_type !== 'channel') return
      if (member.universe_id === null || member.universe_id === undefined) return

      if (!universeMap[member.universe_id]) {
        const universe = ioConfig.value.universes.find(u => u.id === member.universe_id)
        universeMap[member.universe_id] = {
          id: member.universe_id,
          label: universe?.label || `Universe ${member.universe_id}`,
          faders: []
        }
      }
      const existingFader = universeMap[member.universe_id].faders.find(f => f.channel === member.channel)
      if (!existingFader && member.channel) {
        universeMap[member.universe_id].faders.push({
          channel: member.channel,
          name: `Ch ${member.channel}`
        })
      }
    })
  })

  // Also add channels from channelLabels (patched fixtures)
  ioConfig.value.universes.forEach(universe => {
    const labels = dmxStore.channelLabels[universe.id] || {}
    const labeledChannels = Object.keys(labels).map(Number).filter(n => !isNaN(n))

    if (labeledChannels.length > 0) {
      if (!universeMap[universe.id]) {
        universeMap[universe.id] = {
          id: universe.id,
          label: universe.label || `Universe ${universe.id}`,
          faders: []
        }
      }
      labeledChannels.forEach(channel => {
        const existingFader = universeMap[universe.id].faders.find(f => f.channel === channel)
        if (!existingFader) {
          universeMap[universe.id].faders.push({
            channel: channel,
            name: `Ch ${channel}`
          })
        }
      })
    }
  })

  return Object.values(universeMap)
    .filter(u => u.id !== null && u.id !== undefined)
    .map(u => ({
      ...u,
      faders: u.faders.sort((a, b) => a.channel - b.channel)
    }))
})

// Computed for FADERS2 values - reads from local outputValues ref for reactivity
const fader2Values = computed(() => {
  const result = {}
  for (const universe of faderUniverses.value) {
    result[universe.id] = outputValues.value[universe.id] || []
  }
  return result
})

// Computed: Connection lines data (INPUT → MAPPING)
const connectionLines = computed(() => {
  const lines = []

  inputUniverses.value.forEach(universe => {
    universe.channels.forEach(ch => {
      // All INPUT → MAPPING lines are dashed (mapping transformation happens at MAPPING → FADERS)
      if (universe.isPassthrough) {
        lines.push({
          srcUniverseId: universe.id,
          srcChannel: ch,
          dstUniverseId: universe.id,
          dstChannel: ch,
          color: getUniverseColorById(universe.id),
          isMapped: false  // Always dashed for INPUT → MAPPING
        })
      }
    })
  })

  return lines
})

// Helper to add a line between two elements
function addLine(lines, srcEl, dstEl, containerRect, color, isMapped, opacity = null, background = false, id = null) {
  if (srcEl && dstEl) {
    const srcRect = srcEl.getBoundingClientRect()
    const dstRect = dstEl.getBoundingClientRect()

    lines.push({
      id,
      x1: srcRect.right - containerRect.left,
      y1: srcRect.top + srcRect.height / 2 - containerRect.top,
      x2: dstRect.left - containerRect.left,
      y2: dstRect.top + dstRect.height / 2 - containerRect.top,
      color,
      isMapped,
      opacity,
      background
    })
  }
}

// Update line positions based on DOM element positions
function updateLinePositions() {
  if (!flowContainer.value) return

  const lines = []
  const containerRect = flowContainer.value.getBoundingClientRect()

  // Build a map of channel to fader channel
  const channelToFader = {}
  faderUniverses.value.forEach(universe => {
    universe.faders.forEach(fader => {
      channelToFader[`${universe.id}-${fader.channel}`] = fader.channel
    })
  })

  // Check unmapped behavior - if "Ignore", only mapped channels continue
  const isPassthroughBehavior = !mappingConfig.value.enabled || mappingConfig.value.unmappedBehavior === 'Passthrough'

  // 1. INPUT → MAPPING lines
  connectionLines.value.forEach(conn => {
    const srcKey = `input-${conn.srcUniverseId}-${conn.srcChannel}`
    const dstKey = `mapping-${conn.dstUniverseId}-${conn.dstChannel}`
    const srcEl = channelRefs.value[srcKey]
    const dstEl = channelRefs.value[dstKey]

    const lineId = `input-mapping-${conn.srcUniverseId}-${conn.srcChannel}`
    addLine(lines, srcEl, dstEl, containerRect, conn.color, conn.isMapped, null, false, lineId)
  })

  // 2. MAPPING → FADERS lines
  mappingUniverses.value.forEach(universe => {
    universe.allChannels.forEach(ch => {
      const mappingKey = `mapping-${universe.id}-${ch}`
      const mappingEl = channelRefs.value[mappingKey]
      const color = getUniverseColorById(universe.id)
      const isMapped = universe.mappedChannels.includes(ch)

      // Only draw lines if channel is mapped OR unmapped behavior is passthrough
      if (!isMapped && !isPassthroughBehavior) return

      if (isMapped && mappingConfig.value.enabled) {
        // Get ALL mapping rules for this source channel (can map to multiple destinations)
        const mappings = mappingConfig.value.mappings.filter(
          m => m.src_universe === universe.id && m.src_channel === ch
        )
        mappings.forEach(mapping => {
          const dstUniverse = mapping.dst_universe || universe.id
          const dstChannel = mapping.dst_channel
          const faderCh = channelToFader[`${dstUniverse}-${dstChannel}`]
          if (faderCh) {
            const faderKey = `fader-${dstUniverse}-${faderCh}`
            const faderEl = channelRefs.value[faderKey]
            const lineId = `mapping-fader-${universe.id}-${ch}-${dstUniverse}-${dstChannel}`
            addLine(lines, mappingEl, faderEl, containerRect, color, true, null, false, lineId)
          }
        })
      } else {
        // Passthrough: connect to same channel
        const faderCh = channelToFader[`${universe.id}-${ch}`]
        if (faderCh) {
          const faderKey = `fader-${universe.id}-${faderCh}`
          const faderEl = channelRefs.value[faderKey]
          const lineId = `mapping-fader-${universe.id}-${ch}-${universe.id}-${ch}`
          addLine(lines, mappingEl, faderEl, containerRect, color, false, null, false, lineId)
        }
      }
    })
  })

  // Build set of group master faders (faders that control a group)
  const groupMasters = new Set()
  activeGroups.value.forEach(group => {
    if (group.masterUniverse && group.masterChannel) {
      groupMasters.add(`${group.masterUniverse}-${group.masterChannel}`)
    }
  })

  // Build set of group member faders (faders controlled by a group)
  const groupMembers = new Set()
  activeGroups.value.forEach(group => {
    group.members.forEach(member => {
      groupMembers.add(`${member.universe_id}-${member.channel}`)
    })
  })

  // 3. FADERS → GROUPS lines (master faders to their groups)
  activeGroups.value.forEach(group => {
    if (group.masterUniverse && group.masterChannel) {
      const faderKey = `fader-${group.masterUniverse}-${group.masterChannel}`
      const faderEl = channelRefs.value[faderKey]
      const groupKey = `group-${group.id}-0`
      const groupEl = channelRefs.value[groupKey]
      const color = group.color || '#6b7280'
      const lineId = `fader-group-${group.masterUniverse}-${group.masterChannel}-${group.id}`
      addLine(lines, faderEl, groupEl, containerRect, color, false, null, false, lineId)
    }
  })

  // 4. GROUPS → FADERS2 lines (groups to member faders)
  activeGroups.value.forEach(group => {
    const groupKey = `group-${group.id}-0`
    const groupEl = channelRefs.value[groupKey]
    const color = group.color || '#6b7280'
    group.members.forEach(member => {
      const fader2Key = `fader2-${member.universe_id}-${member.channel}`
      const fader2El = channelRefs.value[fader2Key]
      const lineId = `group-fader2-${group.id}-${member.universe_id}-${member.channel}`
      addLine(lines, groupEl, fader2El, containerRect, color, false, null, false, lineId)
    })
  })

  // 5. FADERS → FADERS2 lines (only for mapping output channels) - background layer
  faderUniverses.value.forEach(universe => {
    universe.faders.forEach(fader => {
      // Only draw line if this channel is a mapping output (uses same logic as FADERS1 value display)
      if (shouldShowFaderValue(universe.id, fader.channel)) {
        const faderKey = `fader-${universe.id}-${fader.channel}`
        const faderEl = channelRefs.value[faderKey]
        const fader2Key = `fader2-${universe.id}-${fader.channel}`
        const fader2El = channelRefs.value[fader2Key]
        const color = getUniverseColorById(universe.id)
        const lineId = `fader-fader2-${universe.id}-${fader.channel}`
        addLine(lines, faderEl, fader2El, containerRect, color, false, 0.3, true, lineId)
      }
    })
  })

  renderedLines.value = lines
}

// Watch for data changes to update lines
watch([inputUniverses, mappingUniverses, mappingConfig, activeGroups, faderUniverses], () => {
  nextTick(() => {
    updateLinePositions()
  })
}, { deep: true, flush: 'post' })

// Format helpers
function formatInputType(type) {
  const types = { 'artnet_input': 'Art-Net', 'sacn_input': 'sACN', 'none': 'None' }
  return types[type] || type
}

function formatOutputType(type) {
  const types = { 'artnet': 'Art-Net', 'sacn': 'sACN', 'mock': 'Mock', 'dummy': 'Dummy' }
  return types[type] || type
}

// Data loading
async function loadIOConfig() {
  try {
    const response = await fetchWithAuth('/api/io')
    ioConfig.value = await response.json()
  } catch (e) {
    console.error('Failed to load I/O config:', e)
  }
}

async function loadMappings() {
  try {
    const response = await fetchWithAuth('/api/mapping')
    mappingData.value = await response.json()
  } catch (e) {
    console.error('Failed to load mappings:', e)
  }
}

async function loadGroups() {
  try {
    const response = await fetchWithAuth('/api/groups/grids')
    const data = await response.json()
    gridsData.value = data.grids || []
  } catch (e) {
    console.error('Failed to load groups:', e)
  }
}

async function refreshData() {
  loading.value = true
  await Promise.all([
    loadIOConfig(),
    loadMappings(),
    loadGroups()
  ])
  loading.value = false
}

async function loadAllChannelLabels() {
  for (const universe of ioConfig.value.universes) {
    await dmxStore.loadChannelLabels(universe.id)
  }
}

// Poll output values from API for real-time FADERS2 updates
async function pollOutputValues() {
  // Use faderUniverses if available, otherwise fall back to ioConfig universes for grandmaster values
  let universes = faderUniverses.value
  if (universes.length === 0) {
    universes = ioConfig.value.universes || []
  }
  if (universes.length === 0) return

  for (const universe of universes) {
    // Skip universes with invalid IDs
    if (universe.id === undefined || universe.id === null) continue

    try {
      const response = await fetchWithAuth(`/api/dmx/values/${universe.id}`)
      if (response.ok) {
        const data = await response.json()
        outputValues.value = { ...outputValues.value, [universe.id]: data.values }
        // Capture grandmaster values
        if (data.global_grandmaster !== undefined) {
          globalGrandmaster.value = data.global_grandmaster
        }
        if (data.universe_grandmaster !== undefined) {
          universeGrandmasters.value = {
            ...universeGrandmasters.value,
            [universe.id]: data.universe_grandmaster
          }
        }
      }
    } catch (e) {
      // Silently ignore polling errors
    }
  }
}

// Inactivity timeout handling
function resetInactivityTimer() {
  if (inactivityTimeout.value) clearTimeout(inactivityTimeout.value)
  if (pollingPaused.value) return  // Don't restart timer if already paused

  inactivityTimeout.value = setTimeout(() => {
    pollingPaused.value = true
    if (outputPollInterval.value) {
      clearInterval(outputPollInterval.value)
      outputPollInterval.value = null
    }
  }, INACTIVITY_TIMEOUT_MS)
}

function resumePolling() {
  pollingPaused.value = false
  pollOutputValues()  // Fetch immediately
  outputPollInterval.value = setInterval(pollOutputValues, 2000)
  resetInactivityTimer()
}

// WebSocket event handlers
function handleGroupsChanged() { loadGroups() }
function handleIOChanged() { loadIOConfig() }
function handleMappingChanged() { loadMappings() }
async function handlePatchChanged() {
  await loadAllChannelLabels()
}
function handleGroupValueChanged(data) {
  groupValues.value = { ...groupValues.value, [data.group_id]: data.value }
}
function handleGrandmasterChanged(data) {
  if (data.type === 'global') {
    globalGrandmaster.value = data.value
  } else if (data.type === 'universe') {
    universeGrandmasters.value = {
      ...universeGrandmasters.value,
      [data.universe_id]: data.value
    }
  }
}

// DMX value event handlers - must create new object references to trigger Vue reactivity
function handleChannelChange(data) {
  const uid = data.universe_id
  const currentValues = outputValues.value[uid] || new Array(512).fill(0)
  const newValues = [...currentValues]
  newValues[data.channel - 1] = data.value
  outputValues.value = { ...outputValues.value, [uid]: newValues }
}

function handleValues(data) {
  outputValues.value = { ...outputValues.value, [data.universe_id]: [...data.values] }
}

function handleInputValues(data) {
  inputValues.value = { ...inputValues.value, [data.universe_id]: [...data.values] }
}

function handleAllValues(data) {
  const newValues = { ...outputValues.value }
  for (const [uid, values] of Object.entries(data)) {
    newValues[parseInt(uid)] = [...values]
  }
  outputValues.value = newValues
}

function handleAllInputValues(data) {
  const newValues = { ...inputValues.value }
  for (const [uid, values] of Object.entries(data)) {
    newValues[parseInt(uid)] = [...values]
  }
  inputValues.value = newValues
}

// Lifecycle
onMounted(async () => {
  await refreshData()
  await loadAllChannelLabels()

  // Initialize group values from loaded data (iterate through grids)
  const newGroupValues = {}
  for (const grid of gridsData.value) {
    for (const group of grid.groups || []) {
      newGroupValues[group.id] = group.master_value || 0
    }
  }
  groupValues.value = newGroupValues

  // Initialize DMX values from current websocket state
  // Must create new object references to trigger Vue reactivity
  const newOutputValues = {}
  const newInputValues = {}
  ioConfig.value.universes.forEach(u => {
    wsManager.requestValues(u.id)
    wsManager.requestInputValues(u.id)
    newOutputValues[u.id] = wsManager.getUniverseValues(u.id)
    newInputValues[u.id] = wsManager.getInputValues(u.id)
  })
  outputValues.value = newOutputValues
  inputValues.value = newInputValues

  // Start polling output values (reduced frequency, WebSocket handles most updates)
  outputPollInterval.value = setInterval(pollOutputValues, 2000)

  // Start inactivity timer and listen for user activity
  resetInactivityTimer()
  window.addEventListener('mousemove', resetInactivityTimer)
  window.addEventListener('keydown', resetInactivityTimer)
  window.addEventListener('click', resetInactivityTimer)

  // Update line positions after DOM is ready
  nextTick(() => {
    updateLinePositions()
  })
  // Update lines on window resize
  window.addEventListener('resize', updateLinePositions)

  // Subscribe to configuration changes
  wsManager.on('groups_changed', handleGroupsChanged)
  wsManager.on('io_changed', handleIOChanged)
  wsManager.on('mapping_changed', handleMappingChanged)
  wsManager.on('patch_changed', handlePatchChanged)
  wsManager.on('group_value_changed', handleGroupValueChanged)
  wsManager.on('grandmaster_changed', handleGrandmasterChanged)

  // Subscribe to DMX value updates
  wsManager.on('channel_change', handleChannelChange)
  wsManager.on('values', handleValues)
  wsManager.on('all_values', handleAllValues)
  wsManager.on('input_values', handleInputValues)
  wsManager.on('all_input_values', handleAllInputValues)
})

onUnmounted(() => {
  // Stop polling output values
  if (outputPollInterval.value) {
    clearInterval(outputPollInterval.value)
    outputPollInterval.value = null
  }

  // Clear inactivity timeout
  if (inactivityTimeout.value) {
    clearTimeout(inactivityTimeout.value)
    inactivityTimeout.value = null
  }

  // Remove activity listeners
  window.removeEventListener('mousemove', resetInactivityTimer)
  window.removeEventListener('keydown', resetInactivityTimer)
  window.removeEventListener('click', resetInactivityTimer)

  window.removeEventListener('resize', updateLinePositions)
  wsManager.off('groups_changed', handleGroupsChanged)
  wsManager.off('io_changed', handleIOChanged)
  wsManager.off('mapping_changed', handleMappingChanged)
  wsManager.off('patch_changed', handlePatchChanged)
  wsManager.off('group_value_changed', handleGroupValueChanged)
  wsManager.off('grandmaster_changed', handleGrandmasterChanged)

  // Unsubscribe from DMX value updates
  wsManager.off('channel_change', handleChannelChange)
  wsManager.off('values', handleValues)
  wsManager.off('all_values', handleAllValues)
  wsManager.off('input_values', handleInputValues)
  wsManager.off('all_input_values', handleAllInputValues)
})
</script>

<style scoped>
.control-flow-page {
  padding-bottom: 40px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.flow-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px 16px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}

.legend-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
}

.info-banner {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 14px 18px;
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-primary);
}

.info-banner svg {
  flex-shrink: 0;
  margin-top: 2px;
  color: #3b82f6;
}

.info-banner a {
  color: var(--accent);
  text-decoration: underline;
}

/* Flow Container with SVG overlay */
.flow-container {
  position: relative;
}

.connection-lines {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.connection-lines.background-lines {
  z-index: 5;
}

.connection-lines.foreground-lines {
  z-index: 20;
}

/* Flow Columns Layout */
.flow-columns {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  position: relative;
}

.flow-column {
  flex: 0 0 auto;
  min-width: 80px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
}

.flow-column.groups-column {
  position: relative;
  z-index: 15;
}

.column-header {
  padding: 10px 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-secondary);
  border-bottom: 1px solid var(--border);
  text-align: center;
}

.column-content {
  padding: 8px;
  display: flex;
  flex-wrap: wrap;
}

.column-content.vertical-stack {
  flex-direction: column;
  flex-wrap: nowrap;
}

.column-content.no-flex {
  display: block;
}

.flow-arrow {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 4px;
  color: var(--text-secondary);
  min-width: 40px;
}

/* Universe Section - Vertical Layout */
.universe-section {
  display: flex;
  flex-direction: row;
  gap: 0;
  margin-bottom: 8px;
}

.universe-section:last-child {
  margin-bottom: 0;
}

.universe-section.vertical {
  flex-direction: row;
  align-items: stretch;
}

/* Vertical Universe Label */
.universe-label-vertical {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  padding: 4px 4px;
  font-size: 10px;
  font-weight: 600;
  color: white;
  text-align: center;
  border-radius: 4px 0 0 4px;
  min-width: 20px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: space-around;
  white-space: nowrap;
  position: relative;
  z-index: 10;
  opacity: 0.7;
  gap: 8px;
}

.universe-label-vertical .label-repeat {
  padding: 4px 0;
}

.group-label-vertical {
  writing-mode: vertical-rl;
  text-orientation: mixed;
  transform: rotate(180deg);
  padding: 8px 4px;
  font-size: 10px;
  font-weight: 600;
  color: white;
  text-align: center;
  border-radius: 4px 0 0 4px;
  min-width: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.group-label {
  padding: 4px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 11px;
  font-weight: 600;
  color: white;
  border-radius: 4px;
  margin-bottom: 4px;
}

/* Channel Column - Vertical stacking */
.channel-column {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
  background: var(--bg-tertiary);
  border-radius: 0 4px 4px 0;
}

/* Legacy styles for non-vertical sections */
.universe-header {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 12px;
  background: var(--bg-tertiary);
  border-left: 3px solid;
  border-radius: 4px;
  margin-bottom: 8px;
}

.universe-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.universe-info {
  font-size: 11px;
  color: var(--text-secondary);
}

/* Channel Grid - legacy horizontal */
.channel-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.channel-box {
  min-width: 28px;
  padding: 2px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 500;
  border: 1px solid var(--universe-color, var(--border));
  background: color-mix(in srgb, var(--universe-color, var(--border)) 15%, transparent);
  border-radius: 4px;
  color: var(--text-primary);
  cursor: default;
  transition: all 0.15s;
}

.channel-box:hover {
  background: color-mix(in srgb, var(--universe-color, var(--border)) 30%, transparent);
}

/* Hover path highlighting */
.channel-box.highlighted,
.fader-box.highlighted,
.group-label.highlighted,
.master-box-inline.highlighted,
.output-box.highlighted {
  box-shadow: 0 0 8px 2px var(--accent);
  z-index: 10;
  position: relative;
}

.channel-box.locked,
.fader-box.locked,
.group-label.locked,
.master-box-inline.locked,
.output-box.locked {
  box-shadow: 0 0 10px 3px var(--accent), inset 0 0 0 2px var(--accent);
  z-index: 11;
  position: relative;
  cursor: pointer;
}

.channel-box.dimmed,
.fader-box.dimmed,
.group-label.dimmed,
.master-box-inline.dimmed,
.output-box.dimmed {
  opacity: 0.25;
}

/* Make all boxes clickable */
.channel-box,
.fader-box,
.group-label,
.master-box-inline,
.output-box {
  cursor: pointer;
}

line.highlighted {
  filter: drop-shadow(0 0 3px currentColor);
}

.channel-box.patched {
  background: color-mix(in srgb, var(--universe-color, var(--border)) 40%, transparent);
  font-weight: 600;
}

.channel-box.mapped {
  background: rgba(168, 85, 247, 0.3);
  border-color: #a855f7;
}

.channel-box.passthrough {
  background: color-mix(in srgb, var(--universe-color, var(--border)) 25%, transparent);
  border-style: dashed;
}

.channel-box.group-member {
  border-width: 2px;
}

/* Fader box for group names - wider to fit text */
.fader-box {
  position: relative;
  min-width: 50px;
  padding: 2px 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  font-weight: 500;
  border: 1px solid var(--universe-color, var(--border));
  background: color-mix(in srgb, var(--universe-color, var(--border)) 15%, transparent);
  border-radius: 4px;
  color: var(--text-primary);
  cursor: default;
  white-space: nowrap;
  overflow: visible;
}

.fader-box.group-member {
  border-width: 2px;
}

.fader-group-stripe-vertical {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 0 4px 4px 0;
}

.fader-group-stripe-vertical.connects-top {
  top: -4px;
  border-top-right-radius: 0;
}

.fader-group-stripe-vertical.connects-bottom {
  bottom: -4px;
  border-bottom-right-radius: 0;
}

.dmx-value {
  font-size: 7px;
  opacity: 0.7;
  line-height: 1;
  font-family: monospace;
  min-width: 42px;
  text-align: center;
}

.channel-name {
  line-height: 1.2;
}

/* Mapping Section */
.mapping-info-bar {
  width: 100%;
  padding: 6px 10px;
  background: rgba(168, 85, 247, 0.15);
  border: 1px solid rgba(168, 85, 247, 0.3);
  border-radius: 4px;
  margin-bottom: 8px;
}

.mapping-name {
  font-weight: 600;
  font-size: 11px;
  color: #a855f7;
}

/* Group Section - Vertical Layout (same as universe-section) */
.group-section {
  display: flex;
  flex-direction: row;
  gap: 0;
}

.group-section.vertical {
  flex-direction: row;
  align-items: stretch;
}

/* Empty Section */
.empty-section {
  text-align: center;
  padding: 24px 12px;
  color: var(--text-secondary);
  font-size: 13px;
  font-style: italic;
}

/* Masters Section */
/* Output row with inline masters */
.output-column {
  min-width: 200px;
}

.output-row {
  display: flex;
  gap: 2px;
  margin-bottom: 2px;
  align-items: stretch;
}

.master-box-inline {
  position: relative;
  min-width: 40px;
  padding: 2px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  border: 1px solid;
  border-radius: 4px;
}

.master-box-inline.universe-master {
  background: rgba(59, 130, 246, 0.1);
}

.master-box-inline.global-master {
  border-color: #f59e0b;
  background: rgba(245, 158, 11, 0.1);
}

.output-box {
  position: relative;
  min-width: 40px;
  padding: 2px 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 9px;
  border: 2px solid #22c55e;
  border-radius: 4px;
  background: rgba(34, 197, 94, 0.15);
  font-weight: 600;
}

/* Inactivity overlay */
.polling-paused-overlay {
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

.paused-content {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 32px 48px;
  text-align: center;
}

.paused-content p {
  margin: 0 0 20px 0;
  font-size: 16px;
  color: var(--text-secondary);
}

/* Responsive */
@media (max-width: 900px) {
  .flow-columns {
    flex-direction: column;
  }

  .flow-column {
    width: 100%;
  }

  .flow-arrow {
    transform: rotate(90deg);
    padding: 8px;
  }

  .column-content {
    flex-direction: row;
    overflow-x: auto;
  }

  .universe-section.vertical,
  .group-section.vertical {
    flex-direction: column;
  }

  .universe-label-vertical,
  .group-label-vertical {
    writing-mode: horizontal-tb;
    transform: none;
    border-radius: 4px 4px 0 0;
    min-width: auto;
    width: 100%;
  }

  .channel-column {
    border-radius: 0 0 4px 4px;
    flex-direction: row;
    flex-wrap: wrap;
  }
}

/* Status button styles */
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

.btn-bypass-active {
  background: var(--indicator-remote) !important;
  color: white !important;
  animation: pulse-bypass 1.5s infinite;
}

@keyframes pulse-bypass {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.7; }
}
</style>

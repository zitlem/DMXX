<template>
  <div>
    <div class="card-header" style="margin-bottom: 16px;">
      <h2 class="card-title">Input / Output Configuration</h2>
      <div class="header-buttons">
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
      </div>
    </div>

    <!-- Bypass Warning Banner -->
    <div v-if="dmxStore.inputBypassActive" class="bypass-warning-banner">
      <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
        <line x1="12" y1="9" x2="12" y2="13"></line>
        <line x1="12" y1="17" x2="12.01" y2="17"></line>
      </svg>
      <span><strong>Input Bypass Active</strong> - External DMX input is received but NOT applied to faders or output</span>
    </div>

    <!-- MIDI Input Section -->
    <div v-if="midiInputStatus.enabled || midiInputStatus.cc_mappings_count > 0" class="midi-input-section">
      <div class="midi-input-header" @click="toggleMidiInputMonitor">
        <div class="midi-input-title">
          <svg
            class="expand-icon"
            :class="{ expanded: midiInputExpanded }"
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
          <span class="midi-badge">MIDI Input</span>
          <span v-if="midiInputStatus.device_name" class="midi-device">{{ midiInputStatus.device_name }}</span>
          <span v-else class="midi-device disconnected">No device</span>
        </div>
        <div class="midi-input-stats">
          <span class="stat">
            <span class="stat-value">{{ midiInputStatus.cc_mappings_count || 0 }}</span>
            <span class="stat-label">mappings</span>
          </span>
          <span class="stat">
            <span class="stat-value">{{ getMidiActiveChannelCount() }}</span>
            <span class="stat-label">active</span>
          </span>
          <button
            class="btn btn-small"
            :class="midiInputStatus.enabled ? 'btn-success' : 'btn-secondary'"
            @click.stop="toggleMidiInputEnabled"
          >
            {{ midiInputStatus.enabled ? 'On' : 'Off' }}
          </button>
          <router-link to="/midi" class="btn btn-small btn-secondary" @click.stop>Config</router-link>
        </div>
      </div>

      <div v-if="midiInputExpanded" class="midi-input-content">
        <div class="midi-dmx-grid">
          <div
            v-for="channel in 64"
            :key="channel"
            class="midi-dmx-cell"
            :class="{ active: getMidiInputValue(channel) > 0 }"
            :style="getMidiInputCellStyle(channel)"
          >
            <span class="cell-channel">{{ channel }}</span>
            <span class="cell-value">{{ getMidiInputValue(channel) }} | {{ Math.round(getMidiInputValue(channel) / 255 * 100) }}%</span>
          </div>
        </div>
        <p class="midi-help-text">
          MIDI CC messages are mapped to input channels via <router-link to="/midi">MIDI Config</router-link>.
          Use <router-link to="/mapping">Channel Mapping</router-link> to route these to DMX outputs.
        </p>
      </div>
    </div>

    <!-- Universes Layout -->
    <div class="io-grid">
      <!-- Universes Column -->
      <div class="io-column">
        <div class="io-column-header">
          <h3>Universes</h3>
          <div class="global-master-control">
            <span class="global-gm-label">Global</span>
            <input
              type="color"
              class="color-picker"
              :value="dmxStore.globalMasterFaderColor"
              @change="saveGlobalMasterColor($event)"
              title="Global master fader color"
            >
            <input
              type="range"
              class="global-gm-slider"
              min="0"
              max="255"
              :value="dmxStore.globalGrandmaster"
              @input="onGlobalGMChange($event)"
              :style="{ '--slider-color': dmxStore.globalMasterFaderColor }"
            >
            <span class="global-gm-value">{{ Math.round(dmxStore.globalGrandmaster / 255 * 100) }}%</span>
          </div>
          <button class="btn btn-small btn-primary" @click="showAddUniverse = true">+ Add</button>
        </div>
        <div class="io-column-content">
          <div v-for="universe in ioConfig.universes" :key="universe.id" class="universe-card">
            <div class="universe-header">
              <div class="universe-info">
                <span class="universe-label">{{ universe.label }}</span>
                <span class="universe-id">
                  ID: {{ universe.id }}
                  <template v-if="universe.input.input_type === 'artnet_input' && universe.input.config?.artnet_universe !== undefined">
                    (Art-Net U{{ universe.input.config.artnet_universe }})
                  </template>
                  <template v-else-if="universe.input.input_type === 'sacn_input' && universe.input.config?.sacn_universe !== undefined">
                    (sACN U{{ universe.input.config.sacn_universe }})
                  </template>
                </span>
              </div>
              <div class="universe-gm">
                <span class="universe-gm-label">Master</span>
                <input
                  type="color"
                  class="color-picker"
                  :value="universe.master_fader_color || '#00bcd4'"
                  @change="saveUniverseMasterColor(universe.id, $event)"
                  title="Universe master fader color"
                >
                <input
                  type="range"
                  class="universe-gm-slider"
                  min="0"
                  max="255"
                  :value="dmxStore.getUniverseGrandmaster(universe.id)"
                  @input="onUniverseGMChange(universe.id, $event)"
                  :style="{ '--slider-color': universe.master_fader_color || '#00bcd4' }"
                >
                <span class="universe-gm-value">{{ Math.round(dmxStore.getUniverseGrandmaster(universe.id) / 255 * 100) }}%</span>
              </div>
              <div class="universe-actions">
                <button class="btn btn-small btn-secondary" @click="editUniverse(universe)">Edit</button>
                <button class="btn btn-small btn-danger" @click="confirmDeleteUniverse(universe)">Delete</button>
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

            <!-- Input and Outputs Side by Side -->
            <div class="io-sections-row">
              <!-- Input Section -->
              <div class="io-section-row">
                <div class="input-header">
                  <span class="io-section-label">Input</span>
                </div>
                <div class="input-item">
                  <div class="input-info">
                    <select
                      class="form-select io-select"
                      :value="universe.input.input_type"
                      @change="updateInput(universe.id, $event.target.value)"
                    >
                      <option v-for="proto in inputProtocols" :key="proto.id" :value="proto.id">
                        {{ proto.name }}
                      </option>
                    </select>
                    <template v-if="universe.input.input_type !== 'none'">
                      <span class="channel-range-label">Ch</span>
                      <input
                        type="number"
                        class="form-select io-select channel-range-input"
                        :class="{ disabled: universe.input.enabled }"
                        :value="universe.input.channel_start || 1"
                        @change="updateChannelRange(universe.id, parseInt($event.target.value), universe.input.channel_end || 512)"
                        min="1"
                        max="512"
                        :disabled="universe.input.enabled"
                        :title="universe.input.enabled ? 'Turn off input to change channel range' : 'Start channel'"
                      >
                      <span class="channel-range-label">-</span>
                      <input
                        type="number"
                        class="form-select io-select channel-range-input"
                        :class="{ disabled: universe.input.enabled }"
                        :value="universe.input.channel_end || 512"
                        @change="updateChannelRange(universe.id, universe.input.channel_start || 1, parseInt($event.target.value))"
                        min="1"
                        max="512"
                        :disabled="universe.input.enabled"
                        :title="universe.input.enabled ? 'Turn off input to change channel range' : 'End channel'"
                      >
                    </template>
                    <span v-if="universe.input.status" :class="['status-indicator', universe.input.status.running ? 'active' : '']"></span>
                  </div>
                  <div v-if="universe.input.input_type !== 'none'" class="input-controls">
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
                  <option value="output_only">Output Only (no faders)</option>
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
            <input type="text" class="form-input" v-model="inputConfigForm.bind_ip" list="local-ips-artnet" placeholder="0.0.0.0">
            <datalist id="local-ips-artnet">
              <option value="0.0.0.0">All interfaces</option>
              <option v-for="iface in localIPs" :key="iface.ip" :value="iface.ip"></option>
            </datalist>
            <p class="form-help">Available: 0.0.0.0 (all){{ localIPs.length ? ', ' + localIPs.map(i => i.ip).join(', ') : '' }}</p>
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
            <input type="text" class="form-input" v-model="inputConfigForm.bind_ip" list="local-ips-sacn" placeholder="0.0.0.0">
            <datalist id="local-ips-sacn">
              <option value="0.0.0.0">All interfaces</option>
              <option v-for="iface in localIPs" :key="iface.ip" :value="iface.ip"></option>
            </datalist>
            <p class="form-help">Available: 0.0.0.0 (all){{ localIPs.length ? ', ' + localIPs.map(i => i.ip).join(', ') : '' }}</p>
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

        <div v-if="showInputConfig.input.input_type === 'midi_input'" class="config-form">
          <div class="form-group">
            <label class="form-label">MIDI Device</label>
            <select class="form-select" v-model="inputConfigForm.device_name">
              <option value="">Any connected device</option>
              <option v-for="device in midiDevices" :key="device" :value="device">
                {{ device }}
              </option>
            </select>
            <p class="form-help">Select a specific MIDI device or "Any" to accept from all connected devices</p>
          </div>
          <div class="midi-mappings-link">
            <p style="color: var(--text-secondary); margin-bottom: 8px;">
              CC mappings for this universe are configured on the MIDI page.
            </p>
            <router-link to="/midi" class="btn btn-secondary">
              Configure CC Mappings
            </router-link>
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
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useThemeStore } from '../stores/theme.js'
import { useDmxStore } from '../stores/dmx.js'
import { wsManager } from '../websocket.js'

const authStore = useAuthStore()
const themeStore = useThemeStore()
const dmxStore = useDmxStore()

// Check if any channels are parked
const hasParkedChannels = computed(() => {
  return Object.keys(dmxStore.parkedChannels).some(uid =>
    Object.keys(dmxStore.parkedChannels[uid] || {}).length > 0
  )
})

const ioConfig = ref({ universes: [] })
const inputProtocols = ref([])
const outputProtocols = ref([])
const showInputConfig = ref(null)
const showOutputConfig = ref(null)
const inputConfigForm = ref({})
const outputConfigForm = ref({})
const inputChannelStart = ref(1)
const inputChannelEnd = ref(512)

// Input monitor state
const inputMonitorExpanded = reactive({})
const inputValues = reactive({})

// MIDI Input state
const midiInputStatus = ref({
  enabled: false,
  device_name: null,
  cc_mappings_count: 0,
  triggers_count: 0
})
const midiInputExpanded = ref(false)
const midiInputValues = ref([])

// Help modal state
const showLoopbackHelp = ref(false)
const loopbackHelp = ref(null)

// Local IPs for bind IP suggestions
const localIPs = ref([])

// MIDI devices for MIDI input config
const midiDevices = ref([])

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

async function updateChannelRange(universeId, start, end) {
  // Find universe to get current input settings
  const universe = ioConfig.value.universes.find(u => u.id === universeId)
  if (!universe) return

  try {
    await fetchWithAuth(`/api/io/${universeId}/input`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input_type: universe.input.input_type,
        input_config: universe.input.config,
        input_enabled: universe.input.enabled,
        input_channel_start: start || 1,
        input_channel_end: end || 512
      })
    })
    await loadIOConfig()
  } catch (e) {
    console.error('Failed to update channel range:', e)
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
    const response = await fetchWithAuth('/api/help')
    const data = await response.json()
    loopbackHelp.value = data.sections?.loopback_prevention || null
  } catch (e) {
    console.error('Failed to load loopback help:', e)
  }
}

async function loadLocalIPs() {
  try {
    const response = await fetchWithAuth('/api/io/network/interfaces')
    const data = await response.json()
    localIPs.value = data.interfaces || []
  } catch (e) {
    console.error('Failed to load local IPs:', e)
  }
}

async function loadMidiDevices() {
  try {
    const response = await fetchWithAuth('/api/midi/devices')
    if (response.ok) {
      const data = await response.json()
      midiDevices.value = data.inputs || []
    }
  } catch (e) {
    console.error('Failed to load MIDI devices:', e)
  }
}

function configureInput(universe) {
  showInputConfig.value = universe
  inputConfigForm.value = {
    bind_ip: '0.0.0.0',  // Default to all interfaces
    ...universe.input.config
  }
  // Load channel range
  inputChannelStart.value = universe.input.channel_start || 1
  inputChannelEnd.value = universe.input.channel_end || 512

  // Load MIDI devices if this is a MIDI input
  if (universe.input.input_type === 'midi_input') {
    loadMidiDevices()
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
        input_enabled: showInputConfig.value.input.enabled,
        input_channel_start: inputChannelStart.value,
        input_channel_end: inputChannelEnd.value
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
        enabled: false
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

async function toggleBypass() {
  try {
    await dmxStore.toggleInputBypass()
  } catch (e) {
    console.error('Failed to toggle bypass:', e)
  }
}

// MIDI Input functions
async function loadMidiInputStatus() {
  try {
    const response = await fetchWithAuth('/api/midi/input/status')
    if (response.ok) {
      midiInputStatus.value = await response.json()
    }
  } catch (e) {
    console.error('Failed to load MIDI input status:', e)
  }
}

async function loadMidiInputValues() {
  try {
    const response = await fetchWithAuth('/api/midi/input/values')
    if (response.ok) {
      const data = await response.json()
      midiInputValues.value = data.values || []
    }
  } catch (e) {
    console.error('Failed to load MIDI input values:', e)
  }
}

async function toggleMidiInputEnabled() {
  try {
    const endpoint = midiInputStatus.value.enabled ? 'disable' : 'enable'
    await fetchWithAuth(`/api/midi/input/${endpoint}`, { method: 'POST' })
    await loadMidiInputStatus()
  } catch (e) {
    console.error('Failed to toggle MIDI input:', e)
  }
}

function toggleMidiInputMonitor() {
  midiInputExpanded.value = !midiInputExpanded.value
  if (midiInputExpanded.value) {
    loadMidiInputValues()
    // Start polling while expanded
    midiPollInterval = setInterval(loadMidiInputValues, 200)
  } else {
    // Stop polling
    if (midiPollInterval) {
      clearInterval(midiPollInterval)
      midiPollInterval = null
    }
  }
}

function getMidiInputValue(channel) {
  return midiInputValues.value[channel - 1] || 0
}

function getMidiActiveChannelCount() {
  return midiInputValues.value.filter(v => v > 0).length
}

function getMidiInputCellStyle(channel) {
  const value = getMidiInputValue(channel)
  if (value > 0) {
    const intensity = value / 255
    return {
      background: `rgba(147, 51, 234, ${0.3 + intensity * 0.7})`  // Purple for MIDI
    }
  }
  return {}
}

let midiPollInterval = null

function onUniverseGMChange(universeId, event) {
  const value = parseInt(event.target.value)
  dmxStore.setUniverseGrandmaster(universeId, value)
}

function onGlobalGMChange(event) {
  const value = parseInt(event.target.value)
  dmxStore.setGlobalGrandmaster(value)
}

async function saveGlobalMasterColor(event) {
  const color = event.target.value
  await dmxStore.setGlobalMasterFaderColor(color)
}

async function saveUniverseMasterColor(universeId, event) {
  const color = event.target.value
  await dmxStore.setUniverseMasterFaderColor(universeId, color)
  // Reload I/O config to update the local universe data
  await loadIOConfig()
}

onMounted(() => {
  loadIOConfig()
  loadLoopbackHelp()
  loadLocalIPs()
  loadMidiInputStatus()
  dmxStore.checkInputBypassStatus()
  dmxStore.loadGrandmasters()
  dmxStore.loadMasterFaderColors()

  // Subscribe to input value updates
  wsManager.on('input_values', handleInputValues)

  // Request current input values
  wsManager.requestAllInputValues()
})

onUnmounted(() => {
  wsManager.off('input_values', handleInputValues)
  // Clean up all polling intervals
  Object.values(inputPollIntervals).forEach(clearInterval)
  // Clean up MIDI poll interval
  if (midiPollInterval) {
    clearInterval(midiPollInterval)
  }
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
  grid-template-columns: 1fr;
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

/* Global Master Control in header */
.global-master-control {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border-radius: 6px;
  border: 1px solid var(--border);
}

.global-gm-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.global-gm-slider {
  width: 100px;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--bg-primary);
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}

.global-gm-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--slider-color, #f59e0b);
  cursor: pointer;
}

.global-gm-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--slider-color, #f59e0b);
  border: none;
  cursor: pointer;
}

.global-gm-value {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  min-width: 36px;
  text-align: right;
}

/* Color picker styling */
.color-picker {
  width: 24px;
  height: 24px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 4px;
  cursor: pointer;
  background: transparent;
}

.color-picker::-webkit-color-swatch-wrapper {
  padding: 2px;
}

.color-picker::-webkit-color-swatch {
  border-radius: 2px;
  border: none;
}

.io-column-content {
  padding: 12px;
  flex: 1;
  overflow-y: auto;
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

.universe-gm {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
}

.universe-gm-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  text-transform: uppercase;
}

.universe-gm-slider {
  width: 80px;
  height: 6px;
  -webkit-appearance: none;
  appearance: none;
  background: var(--bg-primary);
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}

.universe-gm-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--slider-color, var(--accent));
  cursor: pointer;
}

.universe-gm-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--slider-color, var(--accent));
  border: none;
  cursor: pointer;
}

.universe-gm-value {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  min-width: 36px;
  text-align: right;
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

/* Side-by-side Input/Output Layout */
.io-sections-row {
  display: flex;
  gap: 16px;
}

.io-sections-row > .io-section-row {
  flex: 1;
  margin-bottom: 0;
}

.io-sections-row > .outputs-section {
  flex: 1;
  margin-top: 0;
  padding-top: 0;
  border-top: none;
}

/* Input Section Styles (matching output-item) */
.input-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  min-height: 28px;
}

.input-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  gap: 12px;
}

.input-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.input-controls {
  display: flex;
  gap: 6px;
  align-items: center;
}

/* Inline Channel Range */
.channel-range-label {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  margin-left: 8px;
}

.channel-range-input {
  width: 65px !important;
  min-width: 65px !important;
  text-align: center;
}

.channel-range-input.disabled {
  opacity: 0.5;
  cursor: not-allowed;
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
  min-height: 28px;
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
  grid-template-columns: repeat(auto-fill, minmax(50px, 1fr));
  gap: 3px;
}

.input-dmx-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 6px 4px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  color: var(--text-secondary);
  min-width: 0;
  overflow: hidden;
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
  font-size: 10px;
  font-weight: 500;
  line-height: 1.2;
  white-space: nowrap;
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

/* Bypass button and warning banner */
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

.header-buttons {
  display: flex;
  gap: 8px;
  align-items: center;
}

.bypass-warning-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  margin-bottom: 16px;
  background: rgba(251, 191, 36, 0.15);
  border: 1px solid rgba(251, 191, 36, 0.5);
  border-radius: 8px;
  color: #fbbf24;
  font-size: 14px;
}

.bypass-warning-banner svg {
  flex-shrink: 0;
}

/* Responsive: Stack on small viewports */
@media (max-width: 768px) {
  .io-sections-row {
    flex-direction: column;
  }

  .io-sections-row > .io-section-row {
    margin-bottom: 12px;
  }

  .io-sections-row > .outputs-section {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }
}

/* MIDI Input Section Styles */
.midi-input-section {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 16px;
  overflow: hidden;
}

.midi-input-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  background: var(--bg-tertiary);
}

.midi-input-header:hover {
  background: var(--bg-secondary);
}

.midi-input-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.midi-badge {
  font-weight: 600;
  font-size: 13px;
  color: #9333ea;  /* Purple for MIDI */
  background: rgba(147, 51, 234, 0.1);
  padding: 4px 8px;
  border-radius: 4px;
}

.midi-device {
  font-size: 13px;
  color: var(--text-secondary);
}

.midi-device.disconnected {
  color: var(--text-muted);
  font-style: italic;
}

.midi-input-stats {
  display: flex;
  align-items: center;
  gap: 16px;
}

.midi-input-content {
  padding: 16px;
  border-top: 1px solid var(--border);
}

.midi-dmx-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(50px, 1fr));
  gap: 3px;
  margin-bottom: 12px;
}

.midi-dmx-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 6px 4px;
  background: var(--bg-tertiary);
  border-radius: 3px;
  color: var(--text-secondary);
  min-width: 0;
  overflow: hidden;
}

.midi-dmx-cell.active {
  color: white;
}

.midi-help-text {
  font-size: 12px;
  color: var(--text-secondary);
  margin: 0;
}

.midi-help-text a {
  color: var(--accent);
}

.midi-mappings-link {
  margin-top: 16px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: 6px;
  border: 1px solid var(--border);
}

/* Mobile: Tighter layout for 768px and below */
@media (max-width: 768px) {
  .io-select {
    min-width: 60px;
    font-size: 10px;
    padding: 3px 4px;
  }

  .channel-range-input {
    width: 36px !important;
    min-width: 36px !important;
    max-width: 36px !important;
    font-size: 10px;
    padding: 2px 3px;
    flex: 0 0 36px !important;
  }

  .channel-range-label {
    font-size: 10px;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .input-dmx-grid {
    grid-template-columns: repeat(auto-fill, minmax(35px, 1fr));
  }

  .passthrough-controls {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .passthrough-controls label {
    font-size: 12px;
  }

  /* Input item - everything on one row */
  .input-item {
    display: flex;
    flex-wrap: nowrap;
    gap: 4px;
    padding: 6px;
    align-items: center;
  }

  .input-info {
    display: flex;
    flex-wrap: nowrap;
    gap: 4px;
    align-items: center;
    flex: 1;
    min-width: 0;
  }

  .input-info > .io-select:first-of-type {
    flex: 1;
    min-width: 80px;
  }

  .input-controls {
    display: flex;
    gap: 3px;
    flex-shrink: 0;
  }

  .input-controls .btn {
    font-size: 10px;
    padding: 2px 5px;
  }

  /* Output item - same compact approach */
  .output-item {
    display: flex;
    flex-wrap: nowrap;
    gap: 4px;
    padding: 6px;
    align-items: center;
  }

  .output-info {
    display: flex;
    flex-wrap: nowrap;
    gap: 4px;
    align-items: center;
    flex: 1;
    min-width: 0;
  }

  .output-info > .io-select {
    flex: 1;
    min-width: 60px;
  }

  .output-controls {
    display: flex;
    gap: 3px;
    flex-shrink: 0;
  }

  .output-controls .btn {
    font-size: 10px;
    padding: 2px 5px;
  }

  /* Universe header - label + buttons on top row, master centered below */
  .universe-header {
    flex-wrap: wrap;
    flex-direction: row;
    justify-content: space-between;
    align-items: flex-start;
    gap: 8px;
  }

  .universe-info {
    flex: 1;
  }

  .universe-gm {
    order: 3;
    width: 100%;
    justify-content: center;
  }

  .universe-actions {
    order: 2;
    width: auto;
  }

  .universe-actions .btn {
    font-size: 11px;
    padding: 4px 8px;
  }

  /* IO sections stacking */
  .io-sections-row {
    flex-direction: column;
    gap: 12px;
  }

  .io-section-row,
  .outputs-section {
    width: 100%;
  }

  .output-row {
    flex-wrap: wrap;
    gap: 8px;
  }

  .input-section-row {
    flex-wrap: wrap;
    gap: 8px;
  }

  /* Smaller buttons throughout */
  .btn-small {
    font-size: 11px;
    padding: 4px 8px;
  }

  /* Card header responsive */
  .card-header {
    flex-wrap: wrap;
    gap: 8px;
  }

  .card-title {
    font-size: 16px;
  }
}
</style>

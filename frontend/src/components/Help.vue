<template>
  <div class="help-page">
    <div class="card-header">
      <h2 class="card-title">Help & Documentation</h2>
    </div>

    <div v-if="loading" class="loading">Loading documentation...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else class="help-sections">
      <!-- I/O Signal Flow -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('ioflow')">
          <h3>I/O Signal Flow</h3>
          <span class="toggle-icon">{{ expanded.ioflow ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.ioflow" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.io_flow.description }}</p>

          <div class="flow-list">
            <div v-for="flow in helpData.sections.io_flow.flows" :key="flow.mode" class="flow-item">
              <div class="flow-mode">{{ flow.mode }}</div>
              <pre class="flow-diagram">{{ flow.diagram }}</pre>
              <div class="flow-desc">{{ flow.description }}</div>
            </div>
          </div>

          <div class="note-box">
            <strong>Note:</strong> {{ helpData.sections.io_flow.note }}
          </div>
        </div>
      </div>

      <!-- Grandmasters -->
      <div v-if="helpData.sections.grandmasters" class="help-card">
        <div class="help-card-header" @click="toggleSection('grandmasters')">
          <h3>Grandmasters (Master Faders)</h3>
          <span class="toggle-icon">{{ expanded.grandmasters ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.grandmasters" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.grandmasters.description }}</p>

          <div class="mode-list">
            <div v-for="gm in helpData.sections.grandmasters.types" :key="gm.type" class="mode-item">
              <div class="mode-name">{{ gm.type }}</div>
              <div class="mode-desc">{{ gm.description }}</div>
              <div class="formula">Formula: <code>{{ gm.formula }}</code></div>
            </div>
          </div>

          <div class="example-box">
            <div class="example-label">Combined Formula:</div>
            <code class="formula-code">{{ helpData.sections.grandmasters.combined_formula }}</code>

            <div class="example-label" style="margin-top: 12px;">Example Calculation:</div>
            <div class="example-scenario">
              Channel: {{ helpData.sections.grandmasters.example.channel_value }},
              Universe GM: {{ helpData.sections.grandmasters.example.universe_gm }},
              Global GM: {{ helpData.sections.grandmasters.example.global_gm }}
            </div>
            <div class="formula">{{ helpData.sections.grandmasters.example.calculation }}</div>
            <div class="example-result">→ {{ helpData.sections.grandmasters.example.result }}</div>
          </div>

          <div class="use-cases">
            <div class="use-cases-title">Use Cases:</div>
            <ul>
              <li v-for="useCase in helpData.sections.grandmasters.use_cases" :key="useCase">{{ useCase }}</li>
            </ul>
          </div>
        </div>
      </div>

      <!-- Passthrough Modes -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('passthrough')">
          <h3>Passthrough Modes</h3>
          <span class="toggle-icon">{{ expanded.passthrough ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.passthrough" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.passthrough_modes.description }}</p>

          <div class="mode-list">
            <div v-for="mode in helpData.sections.passthrough_modes.modes" :key="mode.mode" class="mode-item">
              <div class="mode-name">{{ mode.mode }}</div>
              <div class="mode-desc">{{ mode.description }}</div>
            </div>
          </div>

          <div class="example-box">
            <div class="example-label">Example:</div>
            <div class="example-scenario">{{ helpData.sections.passthrough_modes.example.scenario }}</div>
            <div class="example-result">→ {{ helpData.sections.passthrough_modes.example.result }}</div>
          </div>
        </div>
      </div>

      <!-- Merge Modes -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('merge')">
          <h3>Merge Modes</h3>
          <span class="toggle-icon">{{ expanded.merge ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.merge" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.merge_modes.description }}</p>

          <div class="mode-list">
            <div v-for="mode in helpData.sections.merge_modes.modes" :key="mode.mode" class="mode-item">
              <div class="mode-name">{{ mode.mode }}</div>
              <div class="mode-desc">{{ mode.description }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Channel Mapping -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('mapping')">
          <h3>Channel Mapping</h3>
          <span class="toggle-icon">{{ expanded.mapping ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.mapping" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.channel_mapping.description }}</p>
          <p>{{ helpData.sections.channel_mapping.how_it_works }}</p>

          <div class="unmapped-behavior">
            <div class="behavior-title">Unmapped Channel Behavior:</div>
            <div class="behavior-item">
              <span class="behavior-name">Passthrough:</span>
              {{ helpData.sections.channel_mapping.unmapped_behavior.passthrough }}
            </div>
            <div class="behavior-item">
              <span class="behavior-name">Ignore:</span>
              {{ helpData.sections.channel_mapping.unmapped_behavior.ignore }}
            </div>
          </div>
        </div>
      </div>

      <!-- Groups with DMX Input -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('groups')">
          <h3>Groups with DMX Input Link</h3>
          <span class="toggle-icon">{{ expanded.groups ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.groups" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.groups_dmx_input.description }}</p>
          <p>{{ helpData.sections.groups_dmx_input.how_it_works }}</p>

          <div class="example-box">
            <div class="example-label">Example Setup:</div>
            <ul class="setup-list">
              <li v-for="step in helpData.sections.groups_dmx_input.example.setup" :key="step">{{ step }}</li>
            </ul>
            <div class="example-flow">
              <div class="flow-label">Flow:</div>
              {{ helpData.sections.groups_dmx_input.example.flow }}
            </div>
            <div class="example-result">→ {{ helpData.sections.groups_dmx_input.example.result }}</div>
          </div>

          <div class="mode-list">
            <div class="modes-title">Group Modes:</div>
            <div v-for="mode in helpData.sections.groups_dmx_input.group_modes" :key="mode.mode" class="mode-item">
              <div class="mode-name">{{ mode.mode }}</div>
              <div class="mode-desc">{{ mode.description }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input Bypass -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('bypass')">
          <h3>Input Bypass</h3>
          <span class="toggle-icon">{{ expanded.bypass ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.bypass" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.input_bypass.description }}</p>
          <p>{{ helpData.sections.input_bypass.how_it_works }}</p>

          <div class="use-cases">
            <div class="use-cases-title">Use Cases:</div>
            <ul>
              <li v-for="useCase in helpData.sections.input_bypass.use_cases" :key="useCase">{{ useCase }}</li>
            </ul>
          </div>

          <div class="note-box">
            <strong>Note:</strong> {{ helpData.sections.input_bypass.note }}
          </div>
        </div>
      </div>

      <!-- Scene Recall with Active Input -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('sceneRecall')">
          <h3>Scene Recall with Active Input</h3>
          <span class="toggle-icon">{{ expanded.sceneRecall ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.sceneRecall" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.scene_recall_with_input.description }}</p>

          <div class="mode-list">
            <div class="modes-title">Recall Behavior:</div>
            <div v-for="behavior in helpData.sections.scene_recall_with_input.behaviors" :key="behavior.condition" class="mode-item">
              <div class="mode-name">{{ behavior.condition }}</div>
              <div class="mode-desc">{{ behavior.result }}</div>
            </div>
          </div>

          <div class="example-box">
            <div class="example-label">Example:</div>
            <div class="example-scenario">{{ helpData.sections.scene_recall_with_input.example.setup }}</div>
            <div class="behavior-item">
              <span class="behavior-name">Bypass OFF:</span>
              {{ helpData.sections.scene_recall_with_input.example.bypass_off }}
            </div>
            <div class="behavior-item">
              <span class="behavior-name">Bypass ON:</span>
              {{ helpData.sections.scene_recall_with_input.example.bypass_on }}
            </div>
          </div>

          <div class="edge-case-box">
            <div class="edge-case-title">{{ helpData.sections.scene_recall_with_input.edge_case.title }}</div>
            <p>{{ helpData.sections.scene_recall_with_input.edge_case.description }}</p>
            <div class="edge-case-example">
              <strong>Example:</strong> {{ helpData.sections.scene_recall_with_input.edge_case.example }}
            </div>
          </div>

          <div class="group-faders-box">
            <div class="group-faders-title">{{ helpData.sections.scene_recall_with_input.group_faders.title }}</div>
            <p>{{ helpData.sections.scene_recall_with_input.group_faders.description }}</p>
            <div class="note-box">
              <strong>Note:</strong> {{ helpData.sections.scene_recall_with_input.group_faders.note }}
            </div>
          </div>
        </div>
      </div>

      <!-- Loopback Prevention -->
      <div class="help-card">
        <div class="help-card-header" @click="toggleSection('loopback')">
          <h3>Loopback Prevention</h3>
          <span class="toggle-icon">{{ expanded.loopback ? '−' : '+' }}</span>
        </div>
        <div v-if="expanded.loopback" class="help-card-content">
          <p class="section-desc">{{ helpData.sections.loopback_prevention.description }}</p>

          <div class="options-list">
            <div v-for="option in helpData.sections.loopback_prevention.options" :key="option.method" class="option-item">
              <div class="option-method">{{ option.method }}</div>
              <div class="option-desc">{{ option.description }}</div>
              <div class="option-pros-cons">
                <span class="pros">
                  <span class="label">Pros:</span>
                  {{ option.pros.join(', ') }}
                </span>
                <span class="cons">
                  <span class="label">Cons:</span>
                  {{ option.cons.join(', ') }}
                </span>
              </div>
            </div>
          </div>

          <div class="recommendation-box">
            <strong>Recommendation:</strong> {{ helpData.sections.loopback_prevention.recommendation }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()
const loading = ref(true)
const error = ref(null)
const helpData = ref(null)

const expanded = reactive({
  ioflow: true,
  grandmasters: false,
  passthrough: false,
  merge: false,
  mapping: false,
  groups: false,
  bypass: false,
  sceneRecall: false,
  loopback: false
})

function toggleSection(section) {
  expanded[section] = !expanded[section]
}

async function fetchWithAuth(url, options = {}) {
  options.headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, options)
}

async function loadHelp() {
  try {
    loading.value = true
    const response = await fetchWithAuth('/api/help')
    if (!response.ok) {
      throw new Error('Failed to load help documentation')
    }
    helpData.value = await response.json()
  } catch (e) {
    error.value = e.message
    console.error('Failed to load help:', e)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadHelp()
})
</script>

<style scoped>
.help-page {
  max-width: 900px;
  margin: 0 auto;
}

.loading, .error {
  padding: 40px;
  text-align: center;
  color: var(--text-secondary);
}

.error {
  color: var(--error);
}

.help-sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.help-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.help-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}

.help-card-header:hover {
  background: var(--bg-tertiary);
}

.help-card-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.toggle-icon {
  font-size: 20px;
  color: var(--text-secondary);
  width: 24px;
  text-align: center;
}

.help-card-content {
  padding: 0 20px 20px 20px;
  border-top: 1px solid var(--border);
}

.section-desc {
  color: var(--text-secondary);
  margin-top: 16px;
  margin-bottom: 16px;
}

.mode-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 16px 0;
}

.modes-title, .behavior-title, .use-cases-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-primary);
}

.mode-item {
  background: var(--bg-tertiary);
  padding: 12px 16px;
  border-radius: 6px;
  border-left: 3px solid var(--accent);
}

.mode-name {
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 4px;
}

.mode-desc {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.5;
}

.example-box {
  background: rgba(59, 130, 246, 0.1);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 6px;
  padding: 16px;
  margin: 16px 0;
}

.example-label, .flow-label {
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 8px;
}

.example-scenario {
  margin-bottom: 8px;
}

.example-result {
  color: var(--success);
  font-weight: 500;
}

.example-flow {
  margin: 12px 0;
  font-family: monospace;
  font-size: 13px;
  background: var(--bg-primary);
  padding: 8px 12px;
  border-radius: 4px;
}

.setup-list {
  margin: 8px 0;
  padding-left: 20px;
}

.setup-list li {
  margin: 4px 0;
  font-family: monospace;
  font-size: 13px;
}

.unmapped-behavior {
  background: var(--bg-tertiary);
  padding: 12px 16px;
  border-radius: 6px;
  margin: 16px 0;
}

.behavior-item {
  margin: 8px 0;
}

.behavior-name {
  font-weight: 600;
  color: var(--text-primary);
}

.use-cases ul {
  margin: 8px 0;
  padding-left: 20px;
}

.use-cases li {
  margin: 6px 0;
  color: var(--text-secondary);
}

.note-box {
  background: rgba(251, 191, 36, 0.15);
  border: 1px solid rgba(251, 191, 36, 0.3);
  border-radius: 6px;
  padding: 12px 16px;
  margin-top: 16px;
  color: #fbbf24;
}

.options-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 16px 0;
}

.option-item {
  background: var(--bg-tertiary);
  padding: 12px 16px;
  border-radius: 6px;
}

.option-method {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.option-desc {
  color: var(--text-secondary);
  font-size: 14px;
  margin-bottom: 8px;
}

.option-pros-cons {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
}

.option-pros-cons .label {
  font-weight: 600;
}

.pros {
  color: var(--success);
}

.cons {
  color: var(--error);
}

.recommendation-box {
  background: rgba(74, 222, 128, 0.1);
  border: 1px solid rgba(74, 222, 128, 0.3);
  border-radius: 6px;
  padding: 12px 16px;
  margin-top: 16px;
  color: var(--success);
}

/* I/O Flow diagram styles */
.flow-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin: 16px 0;
}

.flow-item {
  background: var(--bg-tertiary);
  padding: 16px;
  border-radius: 8px;
  border-left: 3px solid var(--accent);
}

.flow-mode {
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 8px;
  font-size: 15px;
}

.flow-diagram {
  background: var(--bg-primary);
  padding: 12px 16px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
  white-space: pre;
  overflow-x: auto;
  margin: 8px 0;
  color: var(--text-primary);
  line-height: 1.4;
}

.flow-desc {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.5;
}

/* Edge case and group faders boxes */
.edge-case-box {
  background: rgba(251, 146, 60, 0.1);
  border: 1px solid rgba(251, 146, 60, 0.3);
  border-radius: 6px;
  padding: 16px;
  margin: 16px 0;
}

.edge-case-title {
  font-weight: 600;
  color: #fb923c;
  margin-bottom: 8px;
}

.edge-case-example {
  margin-top: 12px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-primary);
  padding: 8px 12px;
  border-radius: 4px;
}

.group-faders-box {
  background: rgba(74, 222, 128, 0.1);
  border: 1px solid rgba(74, 222, 128, 0.3);
  border-radius: 6px;
  padding: 16px;
  margin: 16px 0;
}

.group-faders-title {
  font-weight: 600;
  color: var(--success);
  margin-bottom: 8px;
}

.group-faders-box .note-box {
  margin-top: 12px;
}

/* Formula styles */
.formula {
  font-family: monospace;
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 6px;
}

.formula code, .formula-code {
  background: var(--bg-primary);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--accent);
}

.formula-code {
  display: block;
  padding: 8px 12px;
  margin-top: 4px;
  font-size: 14px;
}
</style>

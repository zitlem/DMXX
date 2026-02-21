<template>
  <div class="remote-api-container">
    <h2>Remote API</h2>
    <p class="description">
      Create tokens for remote control via HTTP requests. Use these with Home Assistant, StreamDeck, or other automation tools.
    </p>

    <!-- Existing Tokens -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">API Tokens</h3>
      </div>

      <table class="data-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Name</th>
            <th>Target</th>
            <th>Last Used</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="token in remoteTokens" :key="token.id">
            <td><span class="token-type-badge" :class="token.token_type">{{ token.token_type }}</span></td>
            <td class="truncate-cell">{{ token.name || 'Unnamed' }}</td>
            <td class="truncate-cell">{{ getTokenTarget(token) }}</td>
            <td class="truncate-cell">{{ token.last_used ? formatDate(token.last_used) : 'Never' }}</td>
            <td class="action-cell">
              <template v-if="token.token_type === 'blackout'">
                <button class="btn btn-small btn-secondary" @click="copyTokenUrl(token, 'on')">Copy ON</button>
                <button class="btn btn-small btn-secondary" @click="copyTokenUrl(token, 'off')">Copy OFF</button>
              </template>
              <button v-else class="btn btn-small btn-secondary" @click="copyTokenUrl(token)">Copy URL</button>
              <button class="btn btn-small btn-danger" @click="deleteToken(token)">Delete</button>
            </td>
          </tr>
          <tr v-if="remoteTokens.length === 0">
            <td colspan="5" class="empty-message">
              No remote API tokens yet
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Create Token Buttons -->
      <div class="token-actions">
        <button class="btn btn-secondary" @click="showSceneTokenModal = true">
          + Scene Token
        </button>
        <button class="btn btn-secondary" @click="showGroupTokenModal = true">
          + Group Token
        </button>
        <button class="btn btn-secondary" @click="createToken('blackout')">
          + Blackout Token
        </button>
        <button class="btn btn-secondary" @click="createToken('status')">
          + Status Token
        </button>
      </div>
    </div>

    <!-- Usage Examples -->
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Usage Examples</h3>
      </div>
      <div class="examples">
        <div class="example">
          <h4>Trigger Scene</h4>
          <code>GET /api/remote/scene/{"{scene_id}"}?token=xxx</code>
        </div>
        <div class="example">
          <h4>Toggle Blackout</h4>
          <code>GET /api/remote/blackout?token=xxx</code>
          <p>Add <code>&amp;state=on</code> or <code>&amp;state=off</code> to set specific state</p>
        </div>
        <div class="example">
          <h4>Set Group Value</h4>
          <code>GET /api/remote/group/{"{group_id}"}?token=xxx&amp;value=128</code>
          <p>Value is 0-255</p>
        </div>
        <div class="example">
          <h4>Get Status</h4>
          <code>GET /api/remote/status?token=xxx</code>
          <p>Returns current blackout state, groups, and universes</p>
        </div>
      </div>
    </div>

    <!-- Scene Token Modal -->
    <div v-if="showSceneTokenModal" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Create Scene Token</h3>
          <button class="modal-close" @click="showSceneTokenModal = false">&times;</button>
        </div>
        <div class="form-group">
          <label class="form-label">Select Scene</label>
          <select class="form-select" v-model="selectedSceneId">
            <option v-for="scene in scenes" :key="scene.id" :value="scene.id">
              {{ scene.name }}
            </option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Token Name (optional)</label>
          <input type="text" class="form-input" v-model="sceneTokenName" placeholder="e.g., Stage Wash StreamDeck">
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showSceneTokenModal = false">Cancel</button>
          <button class="btn btn-primary" @click="createSceneToken" :disabled="!selectedSceneId">Create</button>
        </div>
      </div>
    </div>

    <!-- Group Token Modal -->
    <div v-if="showGroupTokenModal" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Create Group Token</h3>
          <button class="modal-close" @click="showGroupTokenModal = false">&times;</button>
        </div>
        <div class="form-group">
          <label class="form-label">Select Group</label>
          <select class="form-select" v-model="selectedGroupId">
            <option v-for="group in groups" :key="group.id" :value="group.id">
              {{ group.name }}
            </option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Token Name (optional)</label>
          <input type="text" class="form-input" v-model="groupTokenName" placeholder="e.g., House Lights StreamDeck">
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showGroupTokenModal = false">Cancel</button>
          <button class="btn btn-primary" @click="createGroupToken" :disabled="!selectedGroupId">Create</button>
        </div>
      </div>
    </div>

    <!-- New Token Created Modal -->
    <div v-if="newCreatedToken" class="modal-overlay">
      <div class="modal">
        <div class="modal-header">
          <h3 class="modal-title">Token Created</h3>
          <button class="modal-close" @click="newCreatedToken = null">&times;</button>
        </div>
        <p style="margin-bottom: 12px;">Your new {{ newCreatedToken.token_type }} token has been created.</p>
        <div class="form-group">
          <label class="form-label">Trigger URL</label>
          <div class="token-url-box">
            <code>{{ newCreatedToken.trigger_url }}</code>
          </div>
        </div>
        <p class="warning-text">
          Save this URL now. For security, the full token won't be shown again.
        </p>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="copyNewCreatedTokenUrl">Copy URL</button>
          <button class="btn btn-primary" @click="newCreatedToken = null">Done</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'

const authStore = useAuthStore()

const remoteTokens = ref([])
const groups = ref([])
const scenes = ref([])
const showGroupTokenModal = ref(false)
const showSceneTokenModal = ref(false)
const selectedGroupId = ref(null)
const selectedSceneId = ref(null)
const groupTokenName = ref('')
const sceneTokenName = ref('')
const newCreatedToken = ref(null)

async function fetchWithAuth(url, options = {}) {
  const headers = {
    ...options.headers,
    ...authStore.getAuthHeaders()
  }
  return fetch(url, { ...options, headers })
}

onMounted(async () => {
  await Promise.all([loadRemoteTokens(), loadGroups(), loadScenes()])
})

async function loadRemoteTokens() {
  try {
    const response = await fetchWithAuth('/api/remote/tokens')
    if (response.ok) {
      const data = await response.json()
      remoteTokens.value = data.tokens
    }
  } catch (e) {
    console.error('Failed to load remote tokens:', e)
  }
}

async function loadGroups() {
  try {
    const response = await fetchWithAuth('/api/groups')
    if (response.ok) {
      const data = await response.json()
      groups.value = data.groups.filter(g => g.enabled)
    }
  } catch (e) {
    console.error('Failed to load groups:', e)
  }
}

async function loadScenes() {
  try {
    const response = await fetchWithAuth('/api/scenes')
    if (response.ok) {
      const data = await response.json()
      scenes.value = data.scenes
    }
  } catch (e) {
    console.error('Failed to load scenes:', e)
  }
}

function getTokenTarget(token) {
  if (token.token_type === 'scene') {
    return token.scene_name || `Scene ${token.scene_id}`
  } else if (token.token_type === 'group') {
    return token.group_name || `Group ${token.group_id}`
  } else if (token.token_type === 'blackout') {
    return 'Blackout toggle'
  } else if (token.token_type === 'status') {
    return 'System status'
  }
  return '-'
}

function formatDate(isoString) {
  if (!isoString) return ''
  const date = new Date(isoString)
  return date.toLocaleDateString() + ' ' + date.toLocaleTimeString()
}

async function createToken(tokenType, groupId = null, name = null) {
  try {
    const payload = {
      token_type: tokenType,
      name: name
    }
    if (tokenType === 'group' && groupId) {
      payload.group_id = groupId
    }

    const response = await fetchWithAuth('/api/remote/tokens', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (response.ok) {
      const token = await response.json()
      newCreatedToken.value = token
      await loadRemoteTokens()
    } else {
      const error = await response.json()
      alert(error.detail || 'Failed to create token')
    }
  } catch (e) {
    console.error('Failed to create token:', e)
    alert('Failed to create token')
  }
}

async function createGroupToken() {
  await createToken('group', selectedGroupId.value, groupTokenName.value || null)
  showGroupTokenModal.value = false
  selectedGroupId.value = null
  groupTokenName.value = ''
}

async function createSceneToken() {
  try {
    const payload = {
      token_type: 'scene',
      scene_id: selectedSceneId.value,
      name: sceneTokenName.value || null
    }

    const response = await fetchWithAuth('/api/remote/tokens', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })

    if (response.ok) {
      const token = await response.json()
      newCreatedToken.value = token
      await loadRemoteTokens()
    } else {
      const error = await response.json()
      alert(error.detail || 'Failed to create token')
    }
  } catch (e) {
    console.error('Failed to create token:', e)
    alert('Failed to create token')
  }
  showSceneTokenModal.value = false
  selectedSceneId.value = null
  sceneTokenName.value = ''
}

async function deleteToken(token) {
  if (!confirm(`Delete this ${token.token_type} token? It will stop working immediately.`)) {
    return
  }

  try {
    const response = await fetchWithAuth(`/api/remote/tokens/${token.id}`, {
      method: 'DELETE'
    })
    if (response.ok) {
      await loadRemoteTokens()
    }
  } catch (e) {
    console.error('Failed to delete token:', e)
  }
}

async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch (err) {
    const textArea = document.createElement('textarea')
    textArea.value = text
    textArea.style.position = 'fixed'
    textArea.style.left = '-9999px'
    document.body.appendChild(textArea)
    textArea.select()
    try {
      document.execCommand('copy')
      return true
    } catch (e) {
      return false
    } finally {
      document.body.removeChild(textArea)
    }
  }
}

async function copyTokenUrl(token, state = null) {
  let url = token.trigger_url
  if (state && token.token_type === 'blackout') {
    url = url + `&state=${state}`
  }
  const success = await copyToClipboard(url)
  const label = state ? `Blackout ${state.toUpperCase()}` : 'URL'
  alert(success ? `${label} copied to clipboard!` : 'Failed to copy. Please copy manually.')
}

async function copyNewCreatedTokenUrl() {
  if (newCreatedToken.value) {
    const success = await copyToClipboard(newCreatedToken.value.trigger_url)
    alert(success ? 'URL copied to clipboard!' : 'Failed to copy.')
  }
}
</script>

<style scoped>
.remote-api-container {
  max-width: 900px;
  margin: 0 auto;
}

.description {
  font-size: 14px;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 24px;
  overflow: hidden;
}

.card-header {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.card-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th,
.data-table td {
  padding: 12px 16px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}

.data-table th {
  font-weight: 500;
  color: var(--text-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.action-cell {
  display: flex;
  gap: 8px;
  flex-wrap: nowrap;
}

.action-cell .btn {
  white-space: nowrap;
}

.truncate-cell {
  max-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.empty-message {
  text-align: center;
  color: var(--text-secondary);
}

.token-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding: 16px;
}

.token-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  text-transform: capitalize;
}

.token-type-badge.scene {
  background: rgba(59, 130, 246, 0.2);
  border: 1px solid rgba(59, 130, 246, 0.5);
  color: #93c5fd;
}

.token-type-badge.blackout {
  background: rgba(239, 68, 68, 0.2);
  border: 1px solid rgba(239, 68, 68, 0.5);
  color: #fca5a5;
}

.token-type-badge.group {
  background: rgba(34, 197, 94, 0.2);
  border: 1px solid rgba(34, 197, 94, 0.5);
  color: #86efac;
}

.token-type-badge.status {
  background: rgba(168, 85, 247, 0.2);
  border: 1px solid rgba(168, 85, 247, 0.5);
  color: #d8b4fe;
}

.token-url-box {
  background: var(--bg-primary);
  padding: 12px;
  border-radius: 6px;
  border: 1px solid var(--border);
}

.token-url-box code {
  font-size: 12px;
  word-break: break-all;
  color: var(--text-secondary);
}

.warning-text {
  font-size: 12px;
  color: var(--warning);
  margin-top: 8px;
}

/* Usage examples */
.examples {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.example {
  background: var(--bg-tertiary);
  padding: 12px;
  border-radius: 6px;
}

.example h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  font-weight: 500;
}

.example code {
  display: block;
  background: var(--bg-primary);
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.example p {
  margin: 8px 0 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.example p code {
  display: inline;
  padding: 2px 6px;
  background: var(--bg-primary);
}

/* Mobile responsive */
@media (max-width: 768px) {
  /* Hide Last Used column (4th column) */
  .data-table th:nth-child(4),
  .data-table td:nth-child(4) {
    display: none;
  }

  .action-cell {
    flex-wrap: wrap;
    gap: 4px;
  }

  .action-cell .btn {
    padding: 4px 6px;
    font-size: 10px;
  }

  .truncate-cell {
    max-width: 60px;
  }

  .token-type-badge {
    font-size: 10px;
    padding: 2px 6px;
  }

  .example code {
    font-size: 10px;
    overflow-x: auto;
  }

  .token-actions {
    flex-wrap: wrap;
  }

  .token-actions .btn {
    font-size: 11px;
    padding: 6px 10px;
  }
}
</style>

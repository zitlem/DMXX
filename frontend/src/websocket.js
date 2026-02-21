import { ref, reactive } from 'vue'

class WebSocketManager {
  constructor() {
    this.ws = null
    this.connected = ref(false)
    this.reconnectAttempts = 0
    this.baseReconnectDelay = 1000
    this.maxReconnectDelay = 30000  // Cap at 30 seconds
    this.reconnectTimeout = null
    this.listeners = new Map()
    this.universeValues = reactive({})
    this.inputValues = reactive({})
    this.blackoutActive = ref(false)
    this.clientId = ref(null)  // Our client ID assigned by server
    this.channelSources = reactive({})  // Track source of each channel change
  }

  connect() {
    // Clean up any existing connection first
    if (this.ws) {
      // If already open, nothing to do
      if (this.ws.readyState === WebSocket.OPEN) {
        return
      }
      // Close stale connections that are stuck in CONNECTING or CLOSING states
      try {
        this.ws.close()
      } catch (e) {
        // Ignore close errors
      }
      this.ws = null
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/ws`

    try {
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.connected.value = true
        this.reconnectAttempts = 0  // Reset on successful connection

        // Request initial values for all universes
        this.send({ type: 'get_all_universes' })
      }

      this.ws.onclose = (event) => {
        this.connected.value = false
        this.ws = null
        this.scheduleReconnect()
      }

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        // Error is usually followed by close, but ensure we update state
        this.connected.value = false
      }

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }
    } catch (e) {
      console.error('Failed to create WebSocket:', e)
      this.ws = null
      this.scheduleReconnect()
    }
  }

  disconnect() {
    // Cancel any pending reconnect
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
      this.reconnectTimeout = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.connected.value = false
  }

  scheduleReconnect() {
    // Cancel any existing reconnect timer
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout)
    }

    this.reconnectAttempts++

    // Exponential backoff with cap - never give up
    const delay = Math.min(
      this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      this.maxReconnectDelay
    )

    this.reconnectTimeout = setTimeout(() => {
      this.reconnectTimeout = null
      this.connect()
    }, delay)
  }

  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  handleMessage(message) {
    const { type, data } = message

    switch (type) {
      case 'connected':
        // Server assigned us a client ID
        this.clientId.value = data.client_id
        this.emit('connected', data)
        break

      case 'channel_change':
        this.updateChannel(data.universe_id, data.channel, data.value)
        // Track the source of this channel change
        if (data.source) {
          this.setChannelSource(data.universe_id, data.channel, data.source)
        }
        this.emit('channel_change', data)
        break

      case 'values':
        this.setUniverseValues(data.universe_id, data.values)
        this.emit('values', data)
        break

      case 'all_values':
        for (const [uid, values] of Object.entries(data)) {
          this.setUniverseValues(parseInt(uid), values)
        }
        this.emit('all_values', data)
        break

      case 'blackout':
        this.blackoutActive.value = data.active
        this.emit('blackout', data)
        break

      case 'input_received':
      case 'input_values':
        this.setInputValues(data.universe_id, data.values)
        this.emit('input_values', data)
        break

      case 'input_to_ui':
        // Input values for fader display (when passthrough show_ui is enabled)
        this.setInputValues(data.universe_id, data.values)
        // Mark all channels as coming from input (including zeros)
        const values = data.values
        for (let i = 0; i < values.length; i++) {
          this.setChannelSource(data.universe_id, i + 1, 'input')
        }
        this.emit('input_to_ui', data)
        break

      case 'all_input_values':
        for (const [uid, values] of Object.entries(data)) {
          this.setInputValues(parseInt(uid), values)
        }
        this.emit('all_input_values', data)
        break

      case 'active_scene_changed':
        this.emit('active_scene_changed', data)
        break

      case 'input_bypass_changed':
        this.emit('input_bypass_changed', data)
        break

      case 'highlight_update':
        this.emit('highlight_update', data)
        break

      case 'park_update':
        this.emit('park_update', data)
        break

      default:
        this.emit(type, data)
    }
  }

  updateChannel(universeId, channel, value) {
    if (!this.universeValues[universeId]) {
      this.universeValues[universeId] = new Array(512).fill(0)
    }
    this.universeValues[universeId][channel - 1] = value
  }

  setUniverseValues(universeId, values) {
    this.universeValues[universeId] = [...values]
  }

  getChannelValue(universeId, channel) {
    if (!this.universeValues[universeId]) {
      return 0
    }
    return this.universeValues[universeId][channel - 1] || 0
  }

  getUniverseValues(universeId) {
    return this.universeValues[universeId] || new Array(512).fill(0)
  }

  setInputValues(universeId, values) {
    this.inputValues[universeId] = [...values]
  }

  getInputValues(universeId) {
    return this.inputValues[universeId] || new Array(512).fill(0)
  }

  setChannelSource(universeId, channel, source) {
    if (!this.channelSources[universeId]) {
      this.channelSources[universeId] = {}
    }
    this.channelSources[universeId][channel] = source
  }

  getChannelSource(universeId, channel) {
    return this.channelSources[universeId]?.[channel] || 'unknown'
  }

  isRemoteSource(universeId, channel) {
    const source = this.getChannelSource(universeId, channel)
    // Only external DMX hardware input shows as remote (blue)
    return source === 'input'
  }

  isLocalSource(universeId, channel) {
    const source = this.getChannelSource(universeId, channel)
    // Any DMXX user (local or remote instance) shows as local (green)
    return source.startsWith('user_')
  }

  requestInputValues(universeId) {
    this.send({
      type: 'get_input_values',
      universe_id: universeId
    })
  }

  requestAllInputValues() {
    this.send({ type: 'get_all_input_values' })
  }

  setChannel(universeId, channel, value) {
    this.send({
      type: 'set_channel',
      universe_id: universeId,
      channel: channel,
      value: value
    })
    // Optimistic update
    this.updateChannel(universeId, channel, value)
  }

  setChannels(universeId, values) {
    this.send({
      type: 'set_channels',
      universe_id: universeId,
      values: values
    })
    // Optimistic update
    for (const [channel, value] of Object.entries(values)) {
      this.updateChannel(universeId, parseInt(channel), value)
    }
  }

  requestValues(universeId) {
    this.send({
      type: 'get_values',
      universe_id: universeId
    })
  }

  setActiveScene(sceneId) {
    this.send({
      type: 'set_active_scene',
      scene_id: sceneId
    })
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, [])
    }
    this.listeners.get(event).push(callback)
  }

  off(event, callback) {
    if (!this.listeners.has(event)) return
    const callbacks = this.listeners.get(event)
    const index = callbacks.indexOf(callback)
    if (index > -1) {
      callbacks.splice(index, 1)
    }
  }

  emit(event, data) {
    if (!this.listeners.has(event)) return
    for (const callback of this.listeners.get(event)) {
      callback(data)
    }
  }
}

export const wsManager = new WebSocketManager()

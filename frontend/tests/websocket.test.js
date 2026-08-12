import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { wsManager } from '../src/websocket.js'

/**
 * A stand-in for the browser WebSocket. Instances register themselves on
 * FakeWebSocket.instances so tests can drive open/close/message callbacks.
 */
class FakeWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSING = 2
  static CLOSED = 3
  static instances = []

  constructor(url) {
    this.url = url
    this.readyState = FakeWebSocket.CONNECTING
    this.sent = []
    this.closeCalls = 0
    FakeWebSocket.instances.push(this)
  }

  send(payload) {
    this.sent.push(payload)
  }

  close() {
    this.closeCalls++
    this.readyState = FakeWebSocket.CLOSED
  }

  // -- helpers to simulate the server side --
  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.()
  }

  receive(message) {
    this.onmessage?.({ data: JSON.stringify(message) })
  }

  receiveRaw(data) {
    this.onmessage?.({ data })
  }

  serverClose() {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.({})
  }

  get messages() {
    return this.sent.map((payload) => JSON.parse(payload))
  }
}

/** Reset the singleton between tests - it holds module-level state. */
function resetManager() {
  wsManager.ws = null
  wsManager.connected.value = false
  wsManager.reconnectAttempts = 0
  wsManager.clientId.value = null
  wsManager.blackoutActive.value = false
  wsManager.listeners.clear()
  for (const key of Object.keys(wsManager.universeValues)) delete wsManager.universeValues[key]
  for (const key of Object.keys(wsManager.inputValues)) delete wsManager.inputValues[key]
  for (const key of Object.keys(wsManager.channelSources)) delete wsManager.channelSources[key]
  if (wsManager.reconnectTimeout) {
    clearTimeout(wsManager.reconnectTimeout)
    wsManager.reconnectTimeout = null
  }
}

/** Connect the manager and return the fake socket, already open. */
function connectOpen() {
  wsManager.connect()
  const socket = FakeWebSocket.instances.at(-1)
  socket.open()
  return socket
}

beforeEach(() => {
  FakeWebSocket.instances = []
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.useFakeTimers()
  resetManager()
})

afterEach(() => {
  vi.useRealTimers()
  resetManager()
})

describe('connection lifecycle', () => {
  it('builds a ws:// url from the page location', () => {
    wsManager.connect()
    expect(FakeWebSocket.instances.at(-1).url).toBe(`ws://${window.location.host}/ws`)
  })

  it('uses wss:// on an https page', () => {
    const original = window.location.protocol
    Object.defineProperty(window.location, 'protocol', {
      value: 'https:',
      configurable: true
    })

    wsManager.connect()
    expect(FakeWebSocket.instances.at(-1).url.startsWith('wss://')).toBe(true)

    Object.defineProperty(window.location, 'protocol', {
      value: original,
      configurable: true
    })
  })

  it('marks itself connected and asks for initial values on open', () => {
    const socket = connectOpen()

    expect(wsManager.connected.value).toBe(true)
    expect(socket.messages).toEqual([{ type: 'get_all_universes' }])
  })

  it('does nothing when already open', () => {
    connectOpen()
    wsManager.connect()
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('replaces a socket that is stuck connecting', () => {
    wsManager.connect()
    const stale = FakeWebSocket.instances.at(-1)

    wsManager.connect()

    expect(stale.closeCalls).toBe(1)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('disconnect closes the socket and cancels any pending reconnect', () => {
    const socket = connectOpen()
    socket.serverClose()          // schedules a reconnect
    expect(wsManager.reconnectTimeout).not.toBeNull()

    wsManager.disconnect()

    expect(wsManager.reconnectTimeout).toBeNull()
    expect(wsManager.connected.value).toBe(false)

    vi.advanceTimersByTime(60000)
    expect(FakeWebSocket.instances).toHaveLength(1)   // no reconnect happened
  })

  it('survives a constructor that throws, and retries', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('WebSocket', function Broken() {
      throw new Error('blocked')
    })

    wsManager.connect()
    expect(wsManager.ws).toBeNull()
    expect(wsManager.reconnectTimeout).not.toBeNull()
  })
})

describe('reconnect backoff', () => {
  it('backs off exponentially and caps at 30s', () => {
    const delays = []
    const spy = vi.spyOn(globalThis, 'setTimeout')

    for (let attempt = 0; attempt < 8; attempt++) {
      wsManager.scheduleReconnect()
      delays.push(spy.mock.calls.at(-1)[1])
    }

    expect(delays.slice(0, 6)).toEqual([1000, 2000, 4000, 8000, 16000, 30000])
    expect(delays.every((delay) => delay <= 30000)).toBe(true)
  })

  it('resets the backoff after a successful open', () => {
    wsManager.scheduleReconnect()
    wsManager.scheduleReconnect()
    expect(wsManager.reconnectAttempts).toBe(2)

    connectOpen()
    expect(wsManager.reconnectAttempts).toBe(0)
  })

  it('reconnects when the timer fires', () => {
    const socket = connectOpen()
    socket.serverClose()

    expect(wsManager.connected.value).toBe(false)
    vi.advanceTimersByTime(1000)
    expect(FakeWebSocket.instances).toHaveLength(2)
  })

  it('only keeps one pending reconnect timer', () => {
    wsManager.scheduleReconnect()
    const first = wsManager.reconnectTimeout
    wsManager.scheduleReconnect()

    expect(wsManager.reconnectTimeout).not.toBe(first)
    vi.advanceTimersByTime(60000)
    expect(FakeWebSocket.instances).toHaveLength(1)   // not two
  })
})

describe('sending', () => {
  it('sends json when the socket is open', () => {
    const socket = connectOpen()
    wsManager.send({ type: 'ping' })
    expect(socket.messages.at(-1)).toEqual({ type: 'ping' })
  })

  it('drops messages when there is no socket', () => {
    expect(() => wsManager.send({ type: 'ping' })).not.toThrow()
  })

  it('drops messages while still connecting', () => {
    wsManager.connect()
    const socket = FakeWebSocket.instances.at(-1)

    wsManager.send({ type: 'ping' })
    expect(socket.sent).toEqual([])
  })

  it('setChannel sends and optimistically updates', () => {
    const socket = connectOpen()

    wsManager.setChannel(1, 5, 200)

    expect(socket.messages.at(-1)).toEqual({
      type: 'set_channel', universe_id: 1, channel: 5, value: 200
    })
    expect(wsManager.getChannelValue(1, 5)).toBe(200)
  })

  it('setChannels sends and optimistically updates every channel', () => {
    const socket = connectOpen()

    wsManager.setChannels(1, { 1: 10, 2: 20 })

    expect(socket.messages.at(-1)).toEqual({
      type: 'set_channels', universe_id: 1, values: { 1: 10, 2: 20 }
    })
    expect(wsManager.getChannelValue(1, 1)).toBe(10)
    expect(wsManager.getChannelValue(1, 2)).toBe(20)
  })

  it('request helpers send the documented message shapes', () => {
    const socket = connectOpen()

    wsManager.requestValues(2)
    wsManager.requestInputValues(3)
    wsManager.requestAllInputValues()
    wsManager.setActiveScene(7)

    expect(socket.messages.slice(1)).toEqual([
      { type: 'get_values', universe_id: 2 },
      { type: 'get_input_values', universe_id: 3 },
      { type: 'get_all_input_values' },
      { type: 'set_active_scene', scene_id: 7 }
    ])
  })
})

describe('incoming messages', () => {
  it('stores the client id from the connected message', () => {
    const socket = connectOpen()
    socket.receive({ type: 'connected', data: { client_id: 'abc12345' } })

    expect(wsManager.clientId.value).toBe('abc12345')
  })

  it('applies a channel_change and records its source', () => {
    const socket = connectOpen()
    socket.receive({
      type: 'channel_change',
      data: { universe_id: 1, channel: 3, value: 128, source: 'user_abc' }
    })

    expect(wsManager.getChannelValue(1, 3)).toBe(128)
    expect(wsManager.getChannelSource(1, 3)).toBe('user_abc')
  })

  it('applies a channel_change without a source', () => {
    const socket = connectOpen()
    socket.receive({
      type: 'channel_change',
      data: { universe_id: 1, channel: 3, value: 5 }
    })

    expect(wsManager.getChannelValue(1, 3)).toBe(5)
    expect(wsManager.getChannelSource(1, 3)).toBe('unknown')
  })

  it('replaces a whole universe on values', () => {
    const socket = connectOpen()
    const values = new Array(512).fill(0)
    values[0] = 255

    socket.receive({ type: 'values', data: { universe_id: 1, values } })

    expect(wsManager.getChannelValue(1, 1)).toBe(255)
    expect(wsManager.getUniverseValues(1)).toHaveLength(512)
  })

  it('applies all_values for every universe, keyed numerically', () => {
    const socket = connectOpen()
    socket.receive({
      type: 'all_values',
      data: { 1: new Array(512).fill(1), 2: new Array(512).fill(2) }
    })

    expect(wsManager.getChannelValue(1, 1)).toBe(1)
    expect(wsManager.getChannelValue(2, 1)).toBe(2)
  })

  it('tracks blackout state', () => {
    const socket = connectOpen()

    socket.receive({ type: 'blackout', data: { active: true } })
    expect(wsManager.blackoutActive.value).toBe(true)

    socket.receive({ type: 'blackout', data: { active: false } })
    expect(wsManager.blackoutActive.value).toBe(false)
  })

  it('stores input values from input_received and input_values', () => {
    const socket = connectOpen()
    const values = new Array(512).fill(0)
    values[4] = 77

    socket.receive({ type: 'input_received', data: { universe_id: 1, values } })
    expect(wsManager.getInputValues(1)[4]).toBe(77)

    values[4] = 99
    socket.receive({ type: 'input_values', data: { universe_id: 1, values } })
    expect(wsManager.getInputValues(1)[4]).toBe(99)
  })

  it('marks every channel as input on input_to_ui', () => {
    const socket = connectOpen()
    const values = new Array(512).fill(0)
    values[0] = 42

    socket.receive({ type: 'input_to_ui', data: { universe_id: 1, values } })

    expect(wsManager.getInputValues(1)[0]).toBe(42)
    expect(wsManager.getChannelSource(1, 1)).toBe('input')
    expect(wsManager.getChannelSource(1, 512)).toBe('input')
  })

  it('applies all_input_values for every universe', () => {
    const socket = connectOpen()
    socket.receive({
      type: 'all_input_values',
      data: { 1: new Array(512).fill(3) }
    })

    expect(wsManager.getInputValues(1)[0]).toBe(3)
  })

  it('forwards unknown message types to listeners', () => {
    const socket = connectOpen()
    const seen = []
    wsManager.on('something_new', (data) => seen.push(data))

    socket.receive({ type: 'something_new', data: { hello: true } })

    expect(seen).toEqual([{ hello: true }])
  })

  it('ignores malformed json without dropping the socket', () => {
    const socket = connectOpen()
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => socket.receiveRaw('not json')).not.toThrow()
    expect(errorSpy).toHaveBeenCalled()

    socket.receive({ type: 'blackout', data: { active: true } })
    expect(wsManager.blackoutActive.value).toBe(true)
  })

  it.each([
    'active_scene_changed',
    'input_bypass_changed',
    'highlight_update',
    'park_update'
  ])('emits %s to listeners', (type) => {
    const socket = connectOpen()
    const seen = []
    wsManager.on(type, (data) => seen.push(data))

    socket.receive({ type, data: { value: 1 } })

    expect(seen).toEqual([{ value: 1 }])
  })
})

describe('value accessors', () => {
  it('returns zeros for an unknown universe', () => {
    expect(wsManager.getUniverseValues(99)).toHaveLength(512)
    expect(wsManager.getChannelValue(99, 1)).toBe(0)
    expect(wsManager.getInputValues(99)).toHaveLength(512)
  })

  it('creates the universe frame on first channel update', () => {
    wsManager.updateChannel(4, 10, 55)

    expect(wsManager.getUniverseValues(4)).toHaveLength(512)
    expect(wsManager.getChannelValue(4, 10)).toBe(55)
  })

  it('copies the array it is given rather than aliasing it', () => {
    const values = new Array(512).fill(0)
    wsManager.setUniverseValues(1, values)

    values[0] = 200
    expect(wsManager.getChannelValue(1, 1)).toBe(0)
  })
})

describe('source classification', () => {
  it('treats external input as remote and any user as local', () => {
    wsManager.setChannelSource(1, 1, 'input')
    wsManager.setChannelSource(1, 2, 'user_abc')
    wsManager.setChannelSource(1, 3, 'group')

    expect(wsManager.isRemoteSource(1, 1)).toBe(true)
    expect(wsManager.isLocalSource(1, 1)).toBe(false)

    expect(wsManager.isLocalSource(1, 2)).toBe(true)
    expect(wsManager.isRemoteSource(1, 2)).toBe(false)

    expect(wsManager.isRemoteSource(1, 3)).toBe(false)
    expect(wsManager.isLocalSource(1, 3)).toBe(false)
  })

  it('reports unknown for channels never touched', () => {
    expect(wsManager.getChannelSource(9, 1)).toBe('unknown')
    expect(wsManager.isRemoteSource(9, 1)).toBe(false)
    expect(wsManager.isLocalSource(9, 1)).toBe(false)
  })
})

describe('listeners', () => {
  it('supports several listeners for one event', () => {
    const calls = []
    wsManager.on('values', () => calls.push('a'))
    wsManager.on('values', () => calls.push('b'))

    wsManager.emit('values', {})

    expect(calls).toEqual(['a', 'b'])
  })

  it('off removes only the given callback', () => {
    const calls = []
    const first = () => calls.push('a')
    const second = () => calls.push('b')
    wsManager.on('values', first)
    wsManager.on('values', second)

    wsManager.off('values', first)
    wsManager.emit('values', {})

    expect(calls).toEqual(['b'])
  })

  it('off is safe for unknown events and callbacks', () => {
    expect(() => wsManager.off('nope', () => {})).not.toThrow()
    wsManager.on('values', () => {})
    expect(() => wsManager.off('values', () => {})).not.toThrow()
  })

  it('emit is a no-op when nobody is listening', () => {
    expect(() => wsManager.emit('nobody', {})).not.toThrow()
  })
})

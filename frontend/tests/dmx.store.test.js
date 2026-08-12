import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useDmxStore } from '../src/stores/dmx.js'
import { wsManager } from '../src/websocket.js'

/** Queue of responses, one per fetch call, or a single response for all. */
function stubFetch(responses, { ok = true } = {}) {
  const queue = Array.isArray(responses) ? [...responses] : null
  const spy = vi.fn(async () => ({
    ok,
    json: async () => (queue ? queue.shift() : responses)
  }))
  vi.stubGlobal('fetch', spy)
  return spy
}

/** Capture what the store pushes over the websocket. */
function captureSends() {
  const sent = []
  vi.spyOn(wsManager, 'send').mockImplementation((message) => sent.push(message))
  return sent
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  wsManager.listeners.clear()
  for (const key of Object.keys(wsManager.universeValues)) {
    delete wsManager.universeValues[key]
  }
})

afterEach(() => {
  localStorage.clear()
})

describe('defaults', () => {
  it('starts on universe 1 at full grandmaster', () => {
    const dmx = useDmxStore()

    expect(dmx.currentUniverse).toBe(1)
    expect(dmx.globalGrandmaster).toBe(255)
    expect(dmx.getUniverseGrandmaster(1)).toBe(255)
    expect(dmx.blackoutActive).toBe(false)
    expect(dmx.inputBypassActive).toBe(false)
    expect(dmx.activeScene).toBeNull()
  })
})

describe('loading collections', () => {
  it('loadUniverses keeps the current universe when it still exists', async () => {
    stubFetch({ universes: [{ id: 1 }, { id: 2 }] })
    const dmx = useDmxStore()

    await dmx.loadUniverses()

    expect(dmx.universes).toHaveLength(2)
    expect(dmx.currentUniverse).toBe(1)
  })

  it('loadUniverses falls back to the first universe when the current one is gone', async () => {
    stubFetch({ universes: [{ id: 5 }, { id: 6 }] })
    const dmx = useDmxStore()

    await dmx.loadUniverses()

    expect(dmx.currentUniverse).toBe(5)
  })

  it('loadUniverses leaves state alone on failure', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    const dmx = useDmxStore()

    await dmx.loadUniverses()

    expect(dmx.universes).toEqual([])
  })

  it('loads fixtures, patches and scenes', async () => {
    const dmx = useDmxStore()

    stubFetch({ fixtures: [{ id: 1 }] })
    await dmx.loadFixtures()
    expect(dmx.fixtures).toHaveLength(1)

    stubFetch({ patches: [{ id: 1 }, { id: 2 }] })
    await dmx.loadPatches()
    expect(dmx.patches).toHaveLength(2)

    stubFetch({ scenes: [{ id: 3 }] })
    await dmx.loadScenes()
    expect(dmx.scenes).toHaveLength(1)
  })

  it('sends the auth header on api calls', async () => {
    localStorage.setItem('dmxx_token', 'jwt-token')
    const fetchSpy = stubFetch({ universes: [] })
    const dmx = useDmxStore()

    await dmx.loadUniverses()

    const [, options] = fetchSpy.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer jwt-token')
  })
})

describe('channel labels', () => {
  beforeEach(async () => {
    stubFetch({
      labels: {
        1: { label: 'Par: Red', type: 'color', color: '#ff0000',
             groupColor: '#00ff00', faderName: 'R' },
        2: { label: 'Par: Green', custom_label: 'House left' }
      }
    })
    const dmx = useDmxStore()
    await dmx.loadChannelLabels(1)
  })

  it('prefers a custom label over the patch label', () => {
    const dmx = useDmxStore()
    expect(dmx.getChannelLabel(1, 2)).toBe('House left')
  })

  it('falls back to the patch label, then to a generic name', () => {
    const dmx = useDmxStore()
    expect(dmx.getChannelLabel(1, 1)).toBe('Par: Red')
    expect(dmx.getChannelLabel(1, 99)).toBe('Ch 99')
    expect(dmx.getChannelLabel(9, 1)).toBe('Ch 1')
  })

  it('exposes colour, group colour and fader name', () => {
    const dmx = useDmxStore()

    expect(dmx.getChannelColor(1, 1)).toBe('#ff0000')
    expect(dmx.getChannelGroupColor(1, 1)).toBe('#00ff00')
    expect(dmx.getChannelFaderName(1, 1)).toBe('R')
  })

  it('returns null for channels without those attributes', () => {
    const dmx = useDmxStore()

    expect(dmx.getChannelColor(1, 2)).toBeNull()
    expect(dmx.getChannelGroupColor(1, 2)).toBeNull()
    expect(dmx.getChannelFaderName(1, 2)).toBeNull()
    expect(dmx.getChannelColor(9, 1)).toBeNull()
  })
})

describe('channel writes', () => {
  it('setChannel targets the current universe', () => {
    const spy = vi.spyOn(wsManager, 'setChannel').mockImplementation(() => {})
    const dmx = useDmxStore()
    dmx.currentUniverse = 3

    dmx.setChannel(5, 200)

    expect(spy).toHaveBeenCalledWith(3, 5, 200)
  })

  it('setChannels targets the current universe', () => {
    const spy = vi.spyOn(wsManager, 'setChannels').mockImplementation(() => {})
    const dmx = useDmxStore()
    dmx.currentUniverse = 2

    dmx.setChannels({ 1: 10 })

    expect(spy).toHaveBeenCalledWith(2, { 1: 10 })
  })

  it('reads values back through the websocket cache', () => {
    const dmx = useDmxStore()
    wsManager.setUniverseValues(1, new Array(512).fill(0))
    wsManager.updateChannel(1, 4, 88)

    expect(dmx.getChannelValue(4)).toBe(88)
    expect(dmx.getAllValues()).toHaveLength(512)
  })
})

describe('grandmasters', () => {
  it('clamps the global value and pushes it over the socket', () => {
    const sent = captureSends()
    const dmx = useDmxStore()

    dmx.setGlobalGrandmaster(300)
    expect(dmx.globalGrandmaster).toBe(255)

    dmx.setGlobalGrandmaster(-5)
    expect(dmx.globalGrandmaster).toBe(0)

    expect(sent).toEqual([
      { type: 'set_global_grandmaster', value: 255 },
      { type: 'set_global_grandmaster', value: 0 }
    ])
  })

  it('clamps per-universe values too', () => {
    const sent = captureSends()
    const dmx = useDmxStore()

    dmx.setUniverseGrandmaster(2, 999)

    expect(dmx.getUniverseGrandmaster(2)).toBe(255)
    expect(sent).toEqual([
      { type: 'set_universe_grandmaster', universe_id: 2, value: 255 }
    ])
  })

  it('loads grandmasters from the server', async () => {
    stubFetch({ global: 128, universes: { 1: 64 } })
    const dmx = useDmxStore()

    await dmx.loadGrandmasters()

    expect(dmx.globalGrandmaster).toBe(128)
    expect(dmx.getUniverseGrandmaster(1)).toBe(64)
  })

  it('defaults to full when the server omits the value', async () => {
    stubFetch({ universes: {} })
    const dmx = useDmxStore()

    await dmx.loadGrandmasters()

    expect(dmx.globalGrandmaster).toBe(255)
  })

  it('follows grandmaster changes broadcast by the server', () => {
    const dmx = useDmxStore()

    wsManager.emit('grandmaster_changed', { type: 'global', value: 100 })
    expect(dmx.globalGrandmaster).toBe(100)

    wsManager.emit('grandmaster_changed', {
      type: 'universe', universe_id: 2, value: 50
    })
    expect(dmx.getUniverseGrandmaster(2)).toBe(50)
  })
})

describe('source indicators', () => {
  it('treats another client and external input as remote', () => {
    const dmx = useDmxStore()
    dmx.setMyClientId('mine')
    dmx.setChannelSource(1, 1, 'input')
    dmx.setChannelSource(1, 2, 'user_other')
    dmx.setChannelSource(1, 3, 'user_mine')

    expect(dmx.isRemoteSource(1, 1)).toBe(true)
    expect(dmx.isRemoteSource(1, 2)).toBe(true)
    expect(dmx.isRemoteSource(1, 3)).toBe(false)
  })

  it('treats only this client as local', () => {
    const dmx = useDmxStore()
    dmx.setMyClientId('mine')
    dmx.setChannelSource(1, 3, 'user_mine')
    dmx.setChannelSource(1, 4, 'user_other')

    expect(dmx.isLocalSource(1, 3)).toBe(true)
    expect(dmx.isLocalSource(1, 4)).toBe(false)
  })

  it('reports unknown for untouched channels', () => {
    const dmx = useDmxStore()

    expect(dmx.getChannelSource(1, 1)).toBe('unknown')
    expect(dmx.isRemoteSource(1, 1)).toBe(false)
    expect(dmx.isLocalSource(1, 1)).toBe(false)
  })

  it('does not treat group output as either side', () => {
    const dmx = useDmxStore()
    dmx.setMyClientId('mine')
    dmx.setChannelSource(1, 1, 'group')

    expect(dmx.isRemoteSource(1, 1)).toBe(false)
    expect(dmx.isLocalSource(1, 1)).toBe(false)
  })
})

describe('blackout and bypass', () => {
  it('toggleBlackout adopts the server state', async () => {
    stubFetch({ status: 'activated', blackout: true })
    const dmx = useDmxStore()

    await expect(dmx.toggleBlackout()).resolves.toBe(true)
    expect(dmx.blackoutActive).toBe(true)
  })

  it('checkBlackoutStatus refreshes from the server', async () => {
    stubFetch({ blackout: true })
    const dmx = useDmxStore()

    await dmx.checkBlackoutStatus()

    expect(dmx.blackoutActive).toBe(true)
  })

  it('follows bypass changes broadcast by other clients', () => {
    const dmx = useDmxStore()

    wsManager.emit('input_bypass_changed', { bypass: true })

    expect(dmx.inputBypassActive).toBe(true)
  })
})

describe('parked channels', () => {
  it('loads the parked map for one universe', async () => {
    stubFetch({ universe_id: 1, parked: { 5: 128 } })
    const dmx = useDmxStore()

    await dmx.loadParkedChannels(1)

    expect(dmx.isChannelParked(1, 5)).toBe(true)
    expect(dmx.getParkedValue(1, 5)).toBe(128)
  })

  it('loads and replaces the map for every universe', async () => {
    const dmx = useDmxStore()
    stubFetch({ parked: { 1: { 5: 128 } } })
    await dmx.loadAllParkedChannels()

    stubFetch({ parked: { 2: { 7: 64 } } })
    await dmx.loadAllParkedChannels()

    expect(dmx.isChannelParked(1, 5)).toBe(false)
    expect(dmx.isChannelParked(2, 7)).toBe(true)
  })

  it('parks a channel optimistically once the server accepts', async () => {
    stubFetch({ status: 'parked' })
    const dmx = useDmxStore()

    await dmx.parkChannel(1, 5, 128)

    expect(dmx.isChannelParked(1, 5)).toBe(true)
  })

  it('does not record a park the server rejected', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    stubFetch({ detail: 'denied' }, { ok: false })
    const dmx = useDmxStore()

    await expect(dmx.parkChannel(1, 5, 128)).rejects.toThrow()
    expect(dmx.isChannelParked(1, 5)).toBe(false)
  })

  it('unparks a channel', async () => {
    stubFetch({ status: 'parked' })
    const dmx = useDmxStore()
    await dmx.parkChannel(1, 5, 128)

    stubFetch({ status: 'unparked' })
    await dmx.unparkChannel(1, 5)

    expect(dmx.isChannelParked(1, 5)).toBe(false)
    expect(dmx.getParkedValue(1, 5)).toBeUndefined()
  })

  it('follows park updates broadcast by the server', () => {
    const dmx = useDmxStore()

    wsManager.emit('park_update', {
      universe_id: 1, channel: 3, value: 99, parked: true
    })
    expect(dmx.getParkedValue(1, 3)).toBe(99)

    wsManager.emit('park_update', {
      universe_id: 1, channel: 3, value: null, parked: false
    })
    expect(dmx.isChannelParked(1, 3)).toBe(false)
  })

  it('treats a parked value of zero as parked', () => {
    const dmx = useDmxStore()

    wsManager.emit('park_update', {
      universe_id: 1, channel: 3, value: 0, parked: true
    })

    expect(dmx.isChannelParked(1, 3)).toBe(true)
    expect(dmx.getParkedValue(1, 3)).toBe(0)
  })
})

describe('highlight', () => {
  it('follows highlight updates from the server', () => {
    const dmx = useDmxStore()

    wsManager.emit('highlight_update', {
      active: true, dim_level: 10, channels: { 1: [3, 4] }
    })

    expect(dmx.highlightActive).toBe(true)
    expect(dmx.highlightDimLevel).toBe(10)
    expect(dmx.isChannelHighlighted(1, 3)).toBe(true)
    expect(dmx.isChannelHighlighted(1, 9)).toBe(false)
  })

  it('clears the previous highlight set on each update', () => {
    const dmx = useDmxStore()

    wsManager.emit('highlight_update', { active: true, channels: { 1: [3] } })
    wsManager.emit('highlight_update', { active: true, channels: { 2: [7] } })

    expect(dmx.isChannelHighlighted(1, 3)).toBe(false)
    expect(dmx.isChannelHighlighted(2, 7)).toBe(true)
  })

  it('handles an update with no channels', () => {
    const dmx = useDmxStore()

    wsManager.emit('highlight_update', { active: false })

    expect(dmx.highlightActive).toBe(false)
    expect(dmx.highlightDimLevel).toBe(0)
  })
})

describe('scenes', () => {
  it('createScene appends the new scene', async () => {
    stubFetch({ id: 1, name: 'Look' })
    const dmx = useDmxStore()

    const scene = await dmx.createScene('Look')

    expect(scene.name).toBe('Look')
    expect(dmx.scenes).toHaveLength(1)
  })

  it('createScene sends the documented payload', async () => {
    const fetchSpy = stubFetch({ id: 1 })
    const dmx = useDmxStore()

    await dmx.createScene('Look', 'fade', 1500, [1], [2],
                          { includeGlobalMaster: true })

    const [url, options] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/scenes/save')
    expect(JSON.parse(options.body)).toEqual({
      name: 'Look',
      transition_type: 'fade',
      duration: 1500,
      universe_ids: [1],
      group_ids: [2],
      include_global_master: true,
      include_universe_masters: false
    })
  })

  it('createScene surfaces the server error', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    stubFetch({ detail: 'Name taken' }, { ok: false })
    const dmx = useDmxStore()

    await expect(dmx.createScene('Look')).rejects.toThrow('Name taken')
    expect(dmx.scenes).toEqual([])
  })

  it('updateScene replaces the scene in place', async () => {
    const dmx = useDmxStore()
    stubFetch({ id: 1, name: 'Look' })
    await dmx.createScene('Look')

    stubFetch({ id: 1, name: 'Look v2' })
    await dmx.updateScene(1)

    expect(dmx.scenes).toHaveLength(1)
    expect(dmx.scenes[0].name).toBe('Look v2')
  })

  it('deleteScene drops it from the list', async () => {
    const dmx = useDmxStore()
    stubFetch({ id: 1, name: 'Look' })
    await dmx.createScene('Look')

    stubFetch({ status: 'deleted' })
    await dmx.deleteScene(1)

    expect(dmx.scenes).toEqual([])
  })

  it('tracks the active scene', () => {
    const dmx = useDmxStore()

    dmx.setActiveScene(4)
    expect(dmx.activeScene).toBe(4)

    dmx.clearActiveScene()
    expect(dmx.activeScene).toBeNull()
  })
})

describe('scene recall grace period', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('stays active for the scene duration plus a network buffer', () => {
    const dmx = useDmxStore()

    dmx.startSceneRecallGracePeriod(2000)
    expect(dmx.sceneRecallInProgress).toBe(true)

    vi.advanceTimersByTime(2999)
    expect(dmx.sceneRecallInProgress).toBe(true)

    vi.advanceTimersByTime(2)
    expect(dmx.sceneRecallInProgress).toBe(false)
  })

  it('restarts the window when a second recall lands', () => {
    const dmx = useDmxStore()

    dmx.startSceneRecallGracePeriod(0)
    vi.advanceTimersByTime(900)
    dmx.startSceneRecallGracePeriod(0)

    vi.advanceTimersByTime(900)
    expect(dmx.sceneRecallInProgress).toBe(true)

    vi.advanceTimersByTime(200)
    expect(dmx.sceneRecallInProgress).toBe(false)
  })
})

describe('master fader colours', () => {
  it('falls back to the default universe colour', () => {
    expect(useDmxStore().getUniverseMasterFaderColor(1)).toBe('#00bcd4')
  })

  it('loads colours from settings and the io config', async () => {
    stubFetch([
      { value: '#123456' },
      { universes: [{ id: 1, master_fader_color: '#abcdef' }] }
    ])
    const dmx = useDmxStore()

    await dmx.loadMasterFaderColors()

    expect(dmx.globalMasterFaderColor).toBe('#123456')
    expect(dmx.getUniverseMasterFaderColor(1)).toBe('#abcdef')
  })

  it('stores the global colour after saving', async () => {
    stubFetch({})
    const dmx = useDmxStore()

    await dmx.setGlobalMasterFaderColor('#ff0000')

    expect(dmx.globalMasterFaderColor).toBe('#ff0000')
  })

  it('stores a universe colour after saving', async () => {
    stubFetch({})
    const dmx = useDmxStore()

    await dmx.setUniverseMasterFaderColor(2, '#00ff00')

    expect(dmx.getUniverseMasterFaderColor(2)).toBe('#00ff00')
  })
})

describe('input display', () => {
  it('records input values and display mode per universe', () => {
    const dmx = useDmxStore()

    dmx.setInputDisplayValues(1, [1, 2, 3])
    dmx.setInputDisplayMode(1, true)

    expect(dmx.inputDisplayValues[1]).toEqual([1, 2, 3])
    expect(dmx.inputDisplayMode[1]).toBe(true)
  })
})

describe('highlight control', () => {
  it('loadHighlightState adopts the server state', async () => {
    stubFetch({ active: true, dim_level: 20, channels: { 1: [3, 4] } })
    const dmx = useDmxStore()

    await dmx.loadHighlightState()

    expect(dmx.highlightActive).toBe(true)
    expect(dmx.highlightDimLevel).toBe(20)
    expect(dmx.isChannelHighlighted(1, 4)).toBe(true)
  })

  it('loadHighlightState survives a failure', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    const dmx = useDmxStore()

    await dmx.loadHighlightState()

    expect(dmx.highlightActive).toBe(false)
  })

  it('startHighlight records the channels and dim level', async () => {
    const fetchSpy = stubFetch({ status: 'highlight_started' })
    const dmx = useDmxStore()

    await dmx.startHighlight(1, [3, 4], 15)

    expect(dmx.highlightActive).toBe(true)
    expect(dmx.highlightDimLevel).toBe(15)
    expect(dmx.isChannelHighlighted(1, 3)).toBe(true)

    const [url, options] = fetchSpy.mock.calls[0]
    expect(url).toBe('/api/dmx/highlight')
    expect(JSON.parse(options.body)).toEqual({
      universe_id: 1, channels: [3, 4], dim_level: 15
    })
  })

  it('startHighlight merges without duplicating channels', async () => {
    const dmx = useDmxStore()
    stubFetch({})
    await dmx.startHighlight(1, [3, 4])
    stubFetch({})
    await dmx.startHighlight(1, [4, 5])

    expect(dmx.highlightedChannels[1]).toEqual([3, 4, 5])
  })

  it('startHighlight leaves state alone when the server refuses', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    stubFetch({ detail: 'denied' }, { ok: false })
    const dmx = useDmxStore()

    await expect(dmx.startHighlight(1, [3])).rejects.toThrow()
    expect(dmx.highlightActive).toBe(false)
    expect(dmx.isChannelHighlighted(1, 3)).toBe(false)
  })

  it('addToHighlight appends a channel once', async () => {
    const dmx = useDmxStore()
    stubFetch({})
    await dmx.addToHighlight(1, 7)
    stubFetch({})
    await dmx.addToHighlight(1, 7)

    expect(dmx.highlightActive).toBe(true)
    expect(dmx.highlightedChannels[1]).toEqual([7])
  })

  it('removeFromHighlight drops the channel', async () => {
    const dmx = useDmxStore()
    stubFetch({})
    await dmx.startHighlight(1, [3, 4])

    stubFetch({})
    await dmx.removeFromHighlight(1, 3)

    expect(dmx.isChannelHighlighted(1, 3)).toBe(false)
    expect(dmx.isChannelHighlighted(1, 4)).toBe(true)
    expect(dmx.highlightActive).toBe(true)
  })

  it('removing the last highlighted channel ends highlight mode', async () => {
    const dmx = useDmxStore()
    stubFetch({})
    await dmx.startHighlight(1, [3])

    stubFetch({})
    await dmx.removeFromHighlight(1, 3)

    expect(dmx.highlightActive).toBe(false)
  })

  it('stopHighlight clears everything', async () => {
    const dmx = useDmxStore()
    stubFetch({})
    await dmx.startHighlight(1, [3, 4])

    stubFetch({})
    await dmx.stopHighlight()

    expect(dmx.highlightActive).toBe(false)
    expect(dmx.isChannelHighlighted(1, 3)).toBe(false)
  })

  it('stopHighlight keeps state when the server refuses', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const dmx = useDmxStore()
    stubFetch({})
    await dmx.startHighlight(1, [3])

    stubFetch({ detail: 'denied' }, { ok: false })
    await expect(dmx.stopHighlight()).rejects.toThrow()
    expect(dmx.highlightActive).toBe(true)
  })
})

describe('group actions', () => {
  it.each([
    ['highlightGroup', '/api/groups/4/highlight'],
    ['stopHighlightGroup', '/api/groups/4/highlight/stop'],
    ['parkGroup', '/api/groups/4/park'],
    ['unparkGroup', '/api/groups/4/unpark']
  ])('%s posts to %s', async (method, url) => {
    const fetchSpy = stubFetch({ group_id: 4 })
    const dmx = useDmxStore()

    await dmx[method](4)

    expect(fetchSpy.mock.calls[0][0]).toBe(url)
    expect(fetchSpy.mock.calls[0][1].method).toBe('POST')
  })

  it.each(['highlightGroup', 'stopHighlightGroup', 'parkGroup', 'unparkGroup'])(
    '%s surfaces a refusal', async (method) => {
      vi.spyOn(console, 'error').mockImplementation(() => {})
      stubFetch({ detail: 'Permission denied' }, { ok: false })
      const dmx = useDmxStore()

      await expect(dmx[method](4)).rejects.toThrow()
    })
})

describe('input bypass', () => {
  it('toggleInputBypass adopts the server state', async () => {
    stubFetch({ bypass: true })
    const dmx = useDmxStore()

    await dmx.toggleInputBypass()

    expect(dmx.inputBypassActive).toBe(true)
  })

  it('checkInputBypassStatus refreshes from the server', async () => {
    stubFetch({ bypass: true })
    const dmx = useDmxStore()

    await dmx.checkInputBypassStatus()

    expect(dmx.inputBypassActive).toBe(true)
  })
})

describe('channel label reloads', () => {
  it('reloadAllChannelLabels refetches every loaded universe', async () => {
    const dmx = useDmxStore()
    stubFetch({ labels: { 1: { label: 'A' } } })
    await dmx.loadChannelLabels(1)
    await dmx.loadChannelLabels(2)

    const fetchSpy = stubFetch({ labels: { 1: { label: 'B' } } })
    await dmx.reloadAllChannelLabels()

    expect(fetchSpy).toHaveBeenCalledTimes(2)
    expect(dmx.getChannelLabel(1, 1)).toBe('B')
  })
})

import { describe, it, expect } from 'vitest'
import {
  CHANNEL_RE,
  convertDocumentValues,
  diffGroups,
  normName,
  parseGroupText,
  percentToRaw,
  rawToPercent,
  serializeGroups,
  summariseDiff
} from '../src/lib/groupText.js'

const defaultLabel = (uid, ch) => `Ch ${ch}`

function member(universe_id, channel, base_value = 255, extra = {}) {
  return { id: `${universe_id}-${channel}`, universe_id, channel, base_value,
           target_type: 'channel', ...extra }
}

function grid(name, groups = []) {
  return { id: name, name, groups }
}

function group(name, members = [], mode = 'proportional') {
  return { id: name, name, mode, members }
}

// ---------------------------------------------------------------------------
// Value conversion
// ---------------------------------------------------------------------------
describe('value conversion', () => {
  it.each([[0, 0], [255, 100], [128, 50], [64, 25]])(
    'raw %i is %i%%', (raw, pct) => expect(rawToPercent(raw)).toBe(pct))

  it.each([[0, 0], [100, 255], [50, 128]])(
    '%i%% is raw %i', (pct, raw) => expect(percentToRaw(pct)).toBe(raw))

  it('round trips through percent within one step of 1%', () => {
    for (let raw = 0; raw <= 255; raw++) {
      expect(Math.abs(percentToRaw(rawToPercent(raw)) - raw)).toBeLessThanOrEqual(2)
    }
  })

  it('is exact at the endpoints', () => {
    expect(percentToRaw(rawToPercent(0))).toBe(0)
    expect(percentToRaw(rawToPercent(255))).toBe(255)
  })
})

describe('normName', () => {
  it.each([
    ['  Warm  ', 'Warm'],
    ['Main  Hall', 'Main Hall'],
    ['\tStage\nLeft ', 'Stage Left'],
    ['Front of House', 'Front of House']
  ])('normalises %j', (raw, expected) => expect(normName(raw)).toBe(expected))

  it('survives null and undefined', () => {
    expect(normName(null)).toBe('')
    expect(normName(undefined)).toBe('')
  })

  it('matches the rule the backend applies', () => {
    // backend/api/groups.py normalize_name: " ".join(name.split())
    for (const raw of ['  a  b  ', 'a\tb', ' a ', 'a  b  c']) {
      expect(normName(raw)).toBe(raw.split(/\s+/).filter(Boolean).join(' '))
    }
  })
})

// ---------------------------------------------------------------------------
// Serialising
// ---------------------------------------------------------------------------
describe('serializeGroups', () => {
  it('writes grids, groups and channels', () => {
    const text = serializeGroups(
      [grid('Stage', [group('Warm', [member(1, 5, 200)])])], defaultLabel)

    expect(text).toBe('=== Stage\n[Warm] proportional\nU1.5/200')
  })

  it('includes a channel label when one is set', () => {
    const text = serializeGroups(
      [grid('Stage', [group('Warm', [member(1, 5, 200)])])],
      (uid, ch) => 'Front wash')

    expect(text.split('\n')).toContain('Front wash')
  })

  it('omits the default Ch N label', () => {
    const text = serializeGroups(
      [grid('Stage', [group('Warm', [member(1, 5)])])], defaultLabel)

    expect(text).not.toContain('Ch 5')
  })

  it('writes virtual masters as comments', () => {
    const text = serializeGroups([grid('Stage', [group('Masters', [
      { target_type: 'universe_master', target_universe_id: 2 },
      { target_type: 'global_master' }
    ])])], defaultLabel)

    expect(text).toContain('# U2 Master')
    expect(text).toContain('# Global Master')
  })

  it('applies the display conversion', () => {
    const text = serializeGroups(
      [grid('Stage', [group('Warm', [member(1, 5, 128)])])],
      defaultLabel, rawToPercent)

    expect(text).toContain('U1.5/50')
  })

  it('separates grids and groups with blank lines', () => {
    const text = serializeGroups([
      grid('A', [group('G1', [member(1, 1)]), group('G2', [member(1, 2)])]),
      grid('B', [group('G3', [member(1, 3)])])
    ], defaultLabel)

    expect(text).toBe(
      '=== A\n[G1] proportional\nU1.1/255\n\n[G2] proportional\nU1.2/255\n' +
      '\n=== B\n[G3] proportional\nU1.3/255')
  })

  it('handles empty input and empty grids', () => {
    expect(serializeGroups([], defaultLabel)).toBe('')
    expect(serializeGroups([grid('Empty')], defaultLabel)).toBe('=== Empty')
  })
})

// ---------------------------------------------------------------------------
// Parsing
// ---------------------------------------------------------------------------
describe('parseGroupText', () => {
  it('reads grid, group, mode and channels', () => {
    const { parsed, errors } = parseGroupText(
      '=== Stage\n[Warm] follow\nU1.5/200\nU2.6/100')

    expect(errors).toEqual([])
    expect(parsed).toHaveLength(2)
    expect(parsed[0]).toMatchObject({
      gridName: 'Stage', groupName: 'Warm', mode: 'follow',
      universe_id: 1, channel: 5, base_value: 200, label: null
    })
    expect(parsed[1].universe_id).toBe(2)
  })

  it('defaults the mode and the universe', () => {
    const { parsed } = parseGroupText('=== Stage\n[Warm]\n5/128')
    expect(parsed[0].mode).toBe('proportional')
    expect(parsed[0].universe_id).toBe(1)
  })

  it('attaches a preceding line as the channel label', () => {
    const { parsed } = parseGroupText('=== Stage\n[Warm]\nFront wash\nU1.5/200')
    expect(parsed[0].label).toBe('Front wash')
  })

  it('does not carry a label past a blank line', () => {
    const { parsed } = parseGroupText('=== Stage\n[Warm]\nStale\n\nU1.5/200')
    expect(parsed[0].label).toBeNull()
  })

  it('ignores comment lines', () => {
    const { parsed } = parseGroupText(
      '=== Stage\n[Warm]\n# U2 Master\n# Global Master\nU1.5/200')
    expect(parsed).toHaveLength(1)
    expect(parsed[0].label).toBeNull()
  })

  it('normalises names', () => {
    const { parsed } = parseGroupText('===   Main   Hall\n[  Warm  Front ]\nU1.1/1')
    expect(parsed[0].gridName).toBe('Main Hall')
    expect(parsed[0].groupName).toBe('Warm Front')
  })

  it('clamps values into DMX range', () => {
    const { parsed } = parseGroupText('=== S\n[G]\nU1.1/999')
    expect(parsed[0].base_value).toBe(255)
  })

  it('applies the raw conversion', () => {
    const { parsed } = parseGroupText('=== S\n[G]\nU1.1/50', 'Default', percentToRaw)
    expect(parsed[0].base_value).toBe(128)
  })

  it('reports a channel that has no group', () => {
    const { parsed, errors } = parseGroupText('=== Stage\nU1.5/200')
    expect(parsed).toEqual([])
    expect(errors[0]).toMatch(/channel without a group/)
  })

  it('reports a group that has no grid', () => {
    const { errors } = parseGroupText('[Warm]\nU1.5/200')
    expect(errors[0]).toMatch(/not under a === grid header/)
  })

  it('accepts CRLF and CR line endings', () => {
    for (const eol of ['\r\n', '\r']) {
      const { parsed, errors } = parseGroupText(
        ['=== Stage', '[Warm]', 'U1.5/200'].join(eol))
      expect(errors).toEqual([])
      expect(parsed).toHaveLength(1)
    }
  })

  it('records headers that have no channels under them', () => {
    const { parsed, gridNames, groupKeys } =
      parseGroupText('=== Empty Grid\n[Empty Group]')

    expect(parsed).toEqual([])
    expect([...gridNames]).toEqual(['Empty Grid'])
    expect([...groupKeys]).toEqual(['Empty Grid|Empty Group'])
  })

  it('keeps the first mode seen for a group', () => {
    const { groupModes } = parseGroupText('=== S\n[G] follow\nU1.1/1')
    expect(groupModes.get('S|G')).toBe('follow')
  })

  it('handles an empty document', () => {
    const { parsed, errors } = parseGroupText('')
    expect(parsed).toEqual([])
    expect(errors).toEqual([])
  })
})

describe('round trip', () => {
  it('survives serialize -> parse unchanged', () => {
    const grids = [
      grid('Stage', [
        group('Warm', [member(1, 1, 255), member(1, 2, 128)], 'follow'),
        group('Cool', [member(2, 10, 64)])
      ]),
      grid('House', [group('Front', [member(1, 20, 200)])])
    ]

    const { parsed, errors } = parseGroupText(serializeGroups(grids, defaultLabel))

    expect(errors).toEqual([])
    expect(parsed.map(p => [p.gridName, p.groupName, p.universe_id, p.channel, p.base_value]))
      .toEqual([
        ['Stage', 'Warm', 1, 1, 255],
        ['Stage', 'Warm', 1, 2, 128],
        ['Stage', 'Cool', 2, 10, 64],
        ['House', 'Front', 1, 20, 200]
      ])
  })

  it('a round trip produces no changes at all', () => {
    const grids = [grid('Stage', [group('Warm', [member(1, 1, 200), member(1, 2, 50)])])]
    const text = serializeGroups(grids, defaultLabel)
    const { parsed, gridNames, groupKeys } = parseGroupText(text)

    const diff = diffGroups(parsed, grids, { gridNames, groupKeys, getLabel: defaultLabel })

    expect(summariseDiff(diff)).toBe('')
  })

  it('a percent round trip does not spuriously rewrite values', () => {
    // 127 -> 50% -> 128, which must not read as a change
    const grids = [grid('Stage', [group('Warm', [member(1, 1, 127)])])]
    const text = serializeGroups(grids, defaultLabel, rawToPercent)
    const { parsed, gridNames, groupKeys } = parseGroupText(text, 'Default', percentToRaw)

    const diff = diffGroups(parsed, grids, {
      gridNames, groupKeys, getLabel: defaultLabel,
      sameValue: (stored, wanted) => stored === wanted ||
                                     percentToRaw(rawToPercent(stored)) === wanted
    })

    expect(diff.toUpdate).toEqual([])
  })

  it('preserves empty grids and groups', () => {
    const grids = [grid('Empty', [group('NoMembers', [])])]
    const text = serializeGroups(grids, defaultLabel)
    const { parsed, gridNames, groupKeys } = parseGroupText(text)

    const diff = diffGroups(parsed, grids, { gridNames, groupKeys })

    expect(diff.groupsToDelete).toEqual([])
    expect(diff.gridsToDelete).toEqual([])
  })
})

// ---------------------------------------------------------------------------
// Diffing
// ---------------------------------------------------------------------------
describe('diffGroups', () => {
  const grids = [grid('Stage', [group('Warm', [member(1, 1, 255), member(1, 2, 128)])])]

  function diffOf(text, options = {}) {
    const { parsed, gridNames, groupKeys } = parseGroupText(text)
    return diffGroups(parsed, grids, { gridNames, groupKeys, getLabel: defaultLabel, ...options })
  }

  it('detects an added member', () => {
    const diff = diffOf('=== Stage\n[Warm]\nU1.1/255\nU1.2/128\nU1.3/64')
    expect(diff.toAdd).toHaveLength(1)
    expect(diff.toAdd[0].channel).toBe(3)
    expect(diff.toDelete).toEqual([])
  })

  it('detects a removed member', () => {
    const diff = diffOf('=== Stage\n[Warm]\nU1.1/255')
    expect(diff.toDelete).toHaveLength(1)
    expect(diff.toDelete[0].member.channel).toBe(2)
  })

  it('detects a changed value', () => {
    const diff = diffOf('=== Stage\n[Warm]\nU1.1/100\nU1.2/128')
    expect(diff.toUpdate).toHaveLength(1)
    expect(diff.toUpdate[0].base_value).toBe(100)
  })

  it('detects a new grid and group', () => {
    const diff = diffOf('=== Stage\n[Warm]\nU1.1/255\nU1.2/128\n\n=== Balcony\n[Side]\nU1.9/10')
    expect([...diff.newGrids]).toEqual(['Balcony'])
    expect([...diff.newGroups]).toEqual(['Balcony|Side'])
  })

  it('treats a renamed group as a delete plus a create', () => {
    const diff = diffOf('=== Stage\n[Warm Front]\nU1.1/255\nU1.2/128')

    expect([...diff.newGroups]).toEqual(['Stage|Warm Front'])
    expect(diff.groupsToDelete.map(g => g.name)).toEqual(['Warm'])
  })

  it('treats a renamed grid as a delete plus a create', () => {
    const diff = diffOf('=== Stage Left\n[Warm]\nU1.1/255\nU1.2/128')

    expect([...diff.newGrids]).toEqual(['Stage Left'])
    expect(diff.gridsToDelete.map(g => g.name)).toEqual(['Stage'])
    expect(diff.groupsToDelete.map(g => g.name)).toEqual(['Warm'])
  })

  it('deletes a grid whose header was removed', () => {
    const diff = diffOf('')
    expect(diff.gridsToDelete.map(g => g.name)).toEqual(['Stage'])
    expect(diff.groupsToDelete.map(g => g.name)).toEqual(['Warm'])
  })

  it('ignores virtual masters when diffing members', () => {
    const withMasters = [grid('Stage', [group('Warm', [
      member(1, 1, 255),
      { id: 'm', target_type: 'global_master' }
    ])])]
    const { parsed, gridNames, groupKeys } = parseGroupText('=== Stage\n[Warm]\nU1.1/255')

    const diff = diffGroups(parsed, withMasters, { gridNames, groupKeys })

    expect(diff.toDelete).toEqual([])
    expect(diff.toAdd).toEqual([])
  })

  it('matches names irrespective of whitespace', () => {
    const messy = [grid('Main  Hall', [group(' Warm ', [member(1, 1, 255)])])]
    const { parsed, gridNames, groupKeys } = parseGroupText('=== Main Hall\n[Warm]\nU1.1/255')

    const diff = diffGroups(parsed, messy, { gridNames, groupKeys })

    expect(diff.newGrids.size).toBe(0)
    expect(diff.newGroups.size).toBe(0)
    expect(diff.groupsToDelete).toEqual([])
    expect(diff.gridsToDelete).toEqual([])
  })

  it('reports a label that needs setting', () => {
    const diff = diffOf('=== Stage\n[Warm]\nFront wash\nU1.1/255\nU1.2/128')
    expect(diff.toUpdateLabels).toHaveLength(1)
    expect(diff.toUpdateLabels[0].label).toBe('Front wash')
  })

  it('does not rewrite a label that already matches', () => {
    const diff = diffOf('=== Stage\n[Warm]\nFront wash\nU1.1/255\nU1.2/128',
                        { getLabel: () => 'Front wash' })
    expect(diff.toUpdateLabels).toEqual([])
  })

  it('handles an empty starting state', () => {
    const { parsed, gridNames, groupKeys } = parseGroupText('=== New\n[G]\nU1.1/5')
    const diff = diffGroups(parsed, [], { gridNames, groupKeys })

    expect([...diff.newGrids]).toEqual(['New'])
    expect(diff.toAdd).toHaveLength(1)
    expect(diff.gridsToDelete).toEqual([])
  })
})

describe('summariseDiff', () => {
  it('lists every kind of change', () => {
    const grids = [grid('Stage', [group('Warm', [member(1, 1, 255)])])]
    const { parsed, gridNames, groupKeys } =
      parseGroupText('=== Balcony\n[Side]\nU1.9/10')
    const diff = diffGroups(parsed, grids, { gridNames, groupKeys })

    const summary = summariseDiff(diff)
    expect(summary).toContain('1 new grid(s)')
    expect(summary).toContain('1 new group(s)')
    expect(summary).toContain('1 member(s) to add')
    expect(summary).toContain('1 group(s) to delete')
    expect(summary).toContain('1 grid(s) to delete')
  })

  it('is empty when nothing changed', () => {
    expect(summariseDiff({
      newGrids: new Set(), newGroups: new Set(), toAdd: [], toUpdate: [],
      toDelete: [], groupsToDelete: [], gridsToDelete: [], toUpdateLabels: []
    })).toBe('')
  })
})

// ---------------------------------------------------------------------------
// Mode switching inside the document
// ---------------------------------------------------------------------------
describe('convertDocumentValues', () => {
  it('rewrites channel values and leaves everything else alone', () => {
    const text = '=== Stage\n[Warm] follow\nFront wash\n# Global Master\nU1.1/255\nU1.2/128'

    const percent = convertDocumentValues(text, 'raw', 'percent')

    expect(percent).toContain('U1.1/100')
    expect(percent).toContain('U1.2/50')
    expect(percent).toContain('=== Stage')
    expect(percent).toContain('[Warm] follow')
    expect(percent).toContain('Front wash')
    expect(percent).toContain('# Global Master')
  })

  it('converts back again', () => {
    const back = convertDocumentValues('U1.1/100\nU1.2/50', 'percent', 'raw')
    expect(back).toBe('U1.1/255\nU1.2/128')
  })

  it('is a no-op when the mode does not change', () => {
    const text = 'U1.1/255'
    expect(convertDocumentValues(text, 'raw', 'raw')).toBe(text)
  })

  it('keeps channels written without a universe prefix', () => {
    expect(convertDocumentValues('5/255', 'raw', 'percent')).toBe('5/100')
  })
})

describe('CHANNEL_RE', () => {
  it.each(['U1.5/128', '5/128', 'U12.512/255'])('matches %s', (line) => {
    expect(CHANNEL_RE.test(line)).toBe(true)
  })

  it.each(['=== Grid', '[Group]', '# Comment', 'Front wash', 'U1.5/', 'U1.5'])(
    'does not match %s', (line) => expect(CHANNEL_RE.test(line)).toBe(false))
})

/**
 * Text representation of grids, groups and their channel members.
 *
 * Extracted from Groups.vue so the riskiest part of the app - the bulk apply
 * that can delete groups - is unit testable. Everything here is pure: data in,
 * data out, no component state and no network.
 *
 * Format:
 *
 *   === Grid name
 *   [Group name] mode
 *   Optional channel label
 *   U1.5/128
 *   # U2 Master          <- read-only marker for a virtual master member
 */

export const CHANNEL_RE = /^(?:U(\d+)\.)?(\d+)\/(\d+)$/
const GRID_RE = /^===\s+(.+)$/
const GROUP_RE = /^\[(.+)\]\s*(\w+)?$/

export function rawToPercent(val) {
  return Math.round((val / 255) * 100)
}

export function percentToRaw(pct) {
  return Math.round((pct / 100) * 255)
}

/**
 * Collapse whitespace in a grid or group name.
 * The backend applies the same rule (normalize_name in api/groups.py) so the
 * two sides agree on identity.
 */
export function normName(s) {
  return String(s ?? '').trim().replace(/\s+/g, ' ')
}

const clampValue = (v) => Math.max(0, Math.min(255, v))

/**
 * Render grids to editable text.
 *
 * @param grids      grid objects, each with .name and .groups
 * @param getLabel   (universeId, channel) => label shown for that channel
 * @param toDisplay  (rawBaseValue) => number written into the text
 */
export function serializeGroups(grids, getLabel, toDisplay = (v) => v) {
  const lines = []
  for (const grid of grids || []) {
    if (lines.length > 0) lines.push('')
    lines.push(`=== ${grid.name}`)
    const groups = grid.groups || []
    for (let gi = 0; gi < groups.length; gi++) {
      const group = groups[gi]
      if (gi > 0) lines.push('')
      lines.push(`[${group.name}] ${group.mode}`)
      for (const member of (group.members || [])) {
        if (member.target_type === 'universe_master') {
          lines.push(`# U${member.target_universe_id} Master`)
          continue
        }
        if (member.target_type === 'global_master') {
          lines.push('# Global Master')
          continue
        }
        const label = getLabel(member.universe_id, member.channel)
        const isDefault = !label || label === `Ch ${member.channel}`
        if (!isDefault) lines.push(label)
        lines.push(`U${member.universe_id}.${member.channel}/${toDisplay(member.base_value)}`)
      }
    }
  }
  return lines.join('\n')
}

/**
 * Rewrite the values in a document between raw (0-255) and percent.
 * Only channel lines are touched; labels, headers and comments pass through.
 */
export function convertDocumentValues(text, fromMode, toMode) {
  if (fromMode === toMode) return text
  return String(text).split('\n').map((line) => {
    const m = line.match(CHANNEL_RE)
    if (!m) return line
    const raw = fromMode === 'percent' ? percentToRaw(parseInt(m[3])) : parseInt(m[3])
    const out = toMode === 'percent' ? rawToPercent(raw) : raw
    return `${m[1] ? `U${m[1]}.` : ''}${parseInt(m[2])}/${out}`
  }).join('\n')
}

/**
 * Parse an edited document.
 *
 * @param text            the document
 * @param defaultGridName grid to attribute entries that precede any === header
 * @param toRaw           (displayValue) => raw 0-255 base value
 * @returns { parsed, errors, gridNames, groupKeys, groupModes }
 *          gridNames/groupKeys carry headers that have no channels under them,
 *          which is what lets an empty grid or group survive a round trip.
 */
export function parseGroupText(text, defaultGridName = 'Default', toRaw = (v) => v) {
  const lines = String(text ?? '').replace(/\r\n?/g, '\n').split('\n')
  const parsed = []
  const errors = []
  const gridNames = new Set()
  const groupKeys = new Set()
  const groupModes = new Map()

  let currentGrid = null
  let currentGroup = null
  let currentGroupMode = 'proportional'
  let pendingLabel = null

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim()

    if (!line) { pendingLabel = null; continue }
    if (line.startsWith('#')) continue          // virtual-master marker

    const gridMatch = line.match(GRID_RE)
    if (gridMatch) {
      currentGrid = normName(gridMatch[1])
      gridNames.add(currentGrid)
      currentGroup = null
      pendingLabel = null
      continue
    }

    const groupMatch = line.match(GROUP_RE)
    if (groupMatch) {
      currentGroup = normName(groupMatch[1])
      currentGroupMode = groupMatch[2] || 'proportional'
      if (!currentGrid) {
        errors.push(`Line ${i + 1}: group "${currentGroup}" is not under a === grid header`)
        currentGroup = null
        continue
      }
      const key = `${currentGrid}|${currentGroup}`
      groupKeys.add(key)
      if (!groupModes.has(key)) groupModes.set(key, currentGroupMode)
      pendingLabel = null
      continue
    }

    const chMatch = line.match(CHANNEL_RE)
    if (chMatch) {
      if (!currentGroup) {
        errors.push(`Line ${i + 1}: channel without a group`)
        pendingLabel = null
        continue
      }
      parsed.push({
        gridName: normName(currentGrid || defaultGridName),
        groupName: currentGroup,
        mode: currentGroupMode,
        universe_id: chMatch[1] ? parseInt(chMatch[1]) : 1,
        channel: parseInt(chMatch[2]),
        base_value: clampValue(toRaw(parseInt(chMatch[3]))),
        label: pendingLabel
      })
      pendingLabel = null
      continue
    }

    pendingLabel = line
  }

  return { parsed, errors, gridNames, groupKeys, groupModes }
}

/**
 * Work out what applying a parsed document would change.
 *
 * Identity is by name, so a rename reads as a delete plus a create. The caller
 * is expected to warn about that: deleting a group orphans any scene that
 * stored a master value for it.
 *
 * @param parsed    entries from parseGroupText
 * @param grids     current grid objects
 * @param options   { gridNames, groupKeys, getLabel, sameValue }
 *                  sameValue(storedRaw, parsedRaw) lets the caller forgive
 *                  percent round-trip rounding.
 */
export function diffGroups(parsed, grids, options = {}) {
  const {
    gridNames = new Set(),
    groupKeys = new Set(),
    getLabel = () => null,
    sameValue = (a, b) => a === b
  } = options

  const existingGrids = new Map()
  const existingGroups = new Map()
  const existingMembers = new Map()

  for (const grid of grids || []) {
    const gn = normName(grid.name)
    existingGrids.set(gn, grid)
    for (const group of (grid.groups || [])) {
      const gpn = normName(group.name)
      existingGroups.set(`${gn}|${gpn}`, group)
      for (const member of (group.members || [])) {
        if ((member.target_type || 'channel') !== 'channel') continue
        existingMembers.set(`${gn}|${gpn}|${member.universe_id}|${member.channel}`,
                            { member, group, grid })
      }
    }
  }

  const desired = new Set()
  const toAdd = []
  const toUpdate = []
  const toUpdateLabels = []
  const newGrids = new Set()
  const newGroups = new Set()

  for (const entry of parsed) {
    const groupKey = `${entry.gridName}|${entry.groupName}`
    const key = `${groupKey}|${entry.universe_id}|${entry.channel}`
    desired.add(key)

    if (!existingGrids.has(entry.gridName)) newGrids.add(entry.gridName)
    if (!existingGroups.has(groupKey)) newGroups.add(groupKey)

    const found = existingMembers.get(key)
    if (found) {
      if (!sameValue(found.member.base_value, entry.base_value)) {
        toUpdate.push({ member: found.member, group: found.group, base_value: entry.base_value })
      }
    } else {
      toAdd.push(entry)
    }

    if (entry.label !== null && entry.label !== undefined) {
      const current = getLabel(entry.universe_id, entry.channel)
      const isDefault = !current || current === `Ch ${entry.channel}`
      if ((isDefault && entry.label) || (!isDefault && entry.label !== current)) {
        toUpdateLabels.push(entry)
      }
    }
  }

  // Headers present without channels still count as "kept"
  for (const name of gridNames) if (!existingGrids.has(name)) newGrids.add(name)
  for (const key of groupKeys) if (!existingGroups.has(key)) newGroups.add(key)

  const toDelete = []
  for (const [key, value] of existingMembers) {
    if (!desired.has(key)) toDelete.push(value)
  }

  const groupsToDelete = []
  for (const [key, group] of existingGroups) {
    if (!groupKeys.has(key)) groupsToDelete.push(group)
  }

  const gridsToDelete = []
  for (const [name, grid] of existingGrids) {
    if (!gridNames.has(name)) gridsToDelete.push(grid)
  }

  return {
    toAdd, toUpdate, toDelete, toUpdateLabels,
    newGrids, newGroups, groupsToDelete, gridsToDelete
  }
}

/** Human-readable summary of a diff, in the order the UI presents it. */
export function summariseDiff(diff) {
  const parts = []
  if (diff.newGrids.size > 0) parts.push(`${diff.newGrids.size} new grid(s)`)
  if (diff.newGroups.size > 0) parts.push(`${diff.newGroups.size} new group(s)`)
  if (diff.toAdd.length > 0) parts.push(`${diff.toAdd.length} member(s) to add`)
  if (diff.toUpdate.length > 0) parts.push(`${diff.toUpdate.length} member(s) to update`)
  if (diff.toDelete.length > 0) parts.push(`${diff.toDelete.length} member(s) to delete`)
  if (diff.groupsToDelete.length > 0) parts.push(`${diff.groupsToDelete.length} group(s) to delete`)
  if (diff.gridsToDelete.length > 0) parts.push(`${diff.gridsToDelete.length} grid(s) to delete`)
  if (diff.toUpdateLabels.length > 0) parts.push(`${diff.toUpdateLabels.length} label(s) to update`)
  return parts.join(', ')
}

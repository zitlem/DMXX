/**
 * Single source of truth for available pages in Access Profiles.
 * When adding a new page, add it here and in backend/config.py
 */
export const PAGES = [
  { id: 'faders', name: 'Faders' },
  { id: 'scenes', name: 'Scenes' },
  { id: 'fixtures', name: 'Fixtures' },
  { id: 'patch', name: 'Patch' },
  { id: 'io', name: 'I/O' },
  { id: 'groups', name: 'Groups' },
  { id: 'midi', name: 'MIDI' },
  { id: 'settings', name: 'Settings' },
  { id: 'monitor', name: 'Network Monitor' },
  { id: 'help', name: 'Help' }
]

export const PAGE_IDS = PAGES.map(p => p.id)

export function getPageLabel(id) {
  return PAGES.find(p => p.id === id)?.name || id
}

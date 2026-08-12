# DMXX frontend test-suite

Unit tests for the plain-JS layer of the Vue app: the WebSocket client, the
Pinia stores, the page registry and the router's authorization guard.

## Running

```bash
cd frontend
npm install
npm test              # once
npm run test:watch    # watch mode
npm run test:coverage # with a coverage table
```

## Layout

| File | Covers |
|------|--------|
| `websocket.test.js` | connection lifecycle, exponential reconnect backoff, every inbound message type, optimistic updates, source classification, listener registry |
| `auth.store.test.js` | localStorage rehydration, page/grid/scene access checks, login, logout, `checkAuth` |
| `dmx.store.test.js` | collection loading, channel labels, grandmaster clamping, source indicators, park, highlight, scenes, the recall grace period |
| `theme.store.test.js` | CSS-variable application, presets, custom colours, the local cache and unsaved-change tracking |
| `pages.config.test.js` | the page registry and `getPageLabel` |
| `router.test.js` | the route table: permissions, names, duplicates |
| `router.guard.test.js` | `router.beforeEach` - the authorization gate |
| `groupText.test.js` | the group text format: serialise, parse, diff, percent/raw conversion |
| `api.test.js` | the shared fetch wrapper that turns a non-2xx response into a thrown error |

## Conventions

- **No network, no real sockets, no timers.** `fetch` and `WebSocket` are
  stubbed per test; timer-driven code (reconnect backoff, the scene-recall
  grace period) runs under `vi.useFakeTimers()`.
- **No components are mounted.** The router tests re-register each route under
  its existing name with a stub component, so navigation exercises the guard
  without pulling in the `.vue` tree.
- Each test gets a fresh Pinia via `setActivePinia(createPinia())`, and
  `localStorage` is cleared around every test. The stores read `localStorage`
  at creation time, so set it *before* calling `useXStore()`.
- `wsManager` is a module singleton; the WebSocket and DMX store tests reset
  its state between tests.
- happy-dom provides no `Storage`, so `tests/setup.js` installs a minimal
  spec-shaped `localStorage` before any store is imported.

## Coverage

96% of `src/**/*.js`.

The `.vue` components have no tests of their own — that needs `@vue/test-utils`
and is a separate piece of work. Where component logic is risky enough to
deserve tests, the fix is to move it out of the SFC: `src/lib/groupText.js`
holds the group text format (serialise, parse, diff) that the bulk editor in
`Groups.vue` runs on, because that code can delete groups and needed to be
testable. `Groups.vue` imports it rather than keeping its own copy.

## Cross-language guards

Two constants are duplicated between this app and the Python backend. Both are
guarded from the **backend** suite, which parses these files and compares:

- `src/config/pages.js` ↔ `backend/config.py` (`test_config.py`)
- the `DARK_THEME` palette in `src/stores/theme.js` ↔ `THEME_PRESETS["dark"]`
  in `backend/api/settings.py` (`test_api_settings.py`)

If you change either constant, change both sides or those tests fail.

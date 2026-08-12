/**
 * Test environment setup.
 *
 * happy-dom does not provide a Storage implementation, and the auth and theme
 * stores read localStorage at module scope, so install a minimal spec-shaped
 * one before any store is imported.
 */
class MemoryStorage {
  #items = new Map()

  get length() {
    return this.#items.size
  }

  key(index) {
    return [...this.#items.keys()][index] ?? null
  }

  getItem(key) {
    return this.#items.has(String(key)) ? this.#items.get(String(key)) : null
  }

  setItem(key, value) {
    this.#items.set(String(key), String(value))
  }

  removeItem(key) {
    this.#items.delete(String(key))
  }

  clear() {
    this.#items.clear()
  }
}

if (typeof globalThis.localStorage === 'undefined') {
  const storage = new MemoryStorage()
  globalThis.localStorage = storage
  if (typeof window !== 'undefined') {
    window.localStorage = storage
  }
}

if (typeof globalThis.sessionStorage === 'undefined') {
  globalThis.sessionStorage = new MemoryStorage()
}

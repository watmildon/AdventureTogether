/**
 * Vitest global setup.
 *
 * Node 22+ defines a native `globalThis.localStorage` that is undefined unless Node is
 * started with --localstorage-file. Vitest's jsdom environment does not overwrite globals
 * that already exist, so that undefined value shadows jsdom's working Storage and every
 * test touching localStorage fails. Re-point the globals at jsdom's implementation, or at
 * a minimal in-memory Storage when jsdom's is unavailable.
 */

class MemoryStorage implements Storage {
  private store = new Map<string, string>()
  get length() { return this.store.size }
  clear() { this.store.clear() }
  getItem(key: string) { return this.store.has(key) ? this.store.get(key)! : null }
  key(index: number) { return Array.from(this.store.keys())[index] ?? null }
  removeItem(key: string) { this.store.delete(key) }
  setItem(key: string, value: string) { this.store.set(key, String(value)) }
}

for (const name of ['localStorage', 'sessionStorage'] as const) {
  let current: Storage | undefined
  try { current = (globalThis as any)[name] } catch { current = undefined }
  if (current && typeof current.getItem === 'function') continue

  const jsdomStorage = (globalThis as any).document?.defaultView?.[name]
  const replacement: Storage =
    jsdomStorage && typeof jsdomStorage.getItem === 'function' ? jsdomStorage : new MemoryStorage()

  Object.defineProperty(globalThis, name, { value: replacement, configurable: true, writable: true })
}

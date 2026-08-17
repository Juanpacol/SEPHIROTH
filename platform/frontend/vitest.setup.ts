import "@testing-library/jest-dom/vitest";

/** A minimal in-memory localStorage polyfill, force-installed on both
 * `window` and `globalThis`.
 *
 * Node 22+ ships its own experimental global `localStorage` that logs an
 * "ExperimentalWarning" and evaluates to `undefined` unless started with
 * `--localstorage-file` — since Vitest's jsdom environment IS `globalThis`
 * here, that shadows jsdom's own (perfectly good) implementation. Node
 * <22 has no such global at all, so `window.localStorage` is simply
 * undefined there too without an explicit `http://` origin passed to
 * jsdom. Installing our own tiny implementation sidesteps both cases
 * without depending on a Node-version-specific CLI flag (which would
 * need to differ between local Node 26 and CI's Node 20). */
class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }

  clear(): void {
    this.store.clear();
  }

  getItem(key: string): string | null {
    return this.store.has(key) ? this.store.get(key)! : null;
  }

  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }

  removeItem(key: string): void {
    this.store.delete(key);
  }

  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
}

const memoryStorage = new MemoryStorage();
for (const target of [globalThis, window]) {
  Object.defineProperty(target, "localStorage", {
    configurable: true,
    value: memoryStorage,
  });
}

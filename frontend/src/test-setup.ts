/**
 * Test-environment setup.
 *
 * Node interpreters with the built-in Web Storage API (e.g. Node >= 26) expose a
 * `localStorage` accessor on globalThis that resolves to undefined unless
 * `--localstorage-file` is provided. That accessor shadows the jsdom
 * implementation, so tests that touch localStorage fail with
 * "Cannot read properties of undefined (reading 'setItem')". Replace it with an
 * in-memory stand-in whenever the real one is unavailable.
 */
if (typeof localStorage === 'undefined') {
  const store = new Map<string, string>();
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => {
        store.set(key, String(value));
      },
      removeItem: (key: string) => {
        store.delete(key);
      },
      clear: () => store.clear(),
      key: (index: number) => [...store.keys()][index] ?? null,
      get length() {
        return store.size;
      },
    },
  });
}

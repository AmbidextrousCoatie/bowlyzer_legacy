const STORAGE_PREFIX = "hint:dismissed:";
const memoryStore = new Map<string, string>();

function readItem(key: string): string | null {
  if (typeof window !== "undefined") {
    try {
      return window.localStorage.getItem(key);
    } catch {
      // Storage blocked (private mode, SSR).
    }
  }
  return memoryStore.get(key) ?? null;
}

function writeItem(key: string, value: string): void {
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(key, value);
      return;
    } catch {
      // Fall through to memory store.
    }
  }
  memoryStore.set(key, value);
}

export function isHintDismissed(hintId: string): boolean {
  return readItem(`${STORAGE_PREFIX}${hintId}`) === "1";
}

export function dismissHint(hintId: string): void {
  writeItem(`${STORAGE_PREFIX}${hintId}`, "1");
}

/** Test helper — clears in-memory fallback entries. */
export function resetHintStorageForTests(): void {
  memoryStore.clear();
}

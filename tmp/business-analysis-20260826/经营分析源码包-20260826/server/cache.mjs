export class PartitionCache {
  #entries = new Map();
  #inflight = new Map();

  constructor({ ttlMs = 30_000, maxKeys = 80 } = {}) {
    this.ttlMs = ttlMs;
    this.maxKeys = maxKeys;
  }

  get(key, { allowStale = false, ttlMs = this.ttlMs } = {}) {
    const entry = this.#entries.get(key);
    if (!entry) return null;
    const ageMs = Date.now() - entry.storedAt;
    if (!allowStale && ageMs >= ttlMs) return null;
    this.#entries.delete(key);
    this.#entries.set(key, entry);
    return { ...entry, ageMs, stale: ageMs >= ttlMs };
  }

  set(key, value, fetchedAt = new Date().toISOString()) {
    this.#entries.delete(key);
    this.#entries.set(key, { value, fetchedAt, storedAt: Date.now() });
    while (this.#entries.size > this.maxKeys) {
      const oldest = this.#entries.keys().next().value;
      this.#entries.delete(oldest);
    }
  }

  async dedupe(key, loader) {
    if (this.#inflight.has(key)) return this.#inflight.get(key);
    const promise = Promise.resolve().then(loader).finally(() => this.#inflight.delete(key));
    this.#inflight.set(key, promise);
    return promise;
  }

  newest() {
    let newest = null;
    for (const entry of this.#entries.values()) {
      if (!newest || entry.storedAt > newest.storedAt) newest = entry;
    }
    return newest ? { ...newest, ageMs: Date.now() - newest.storedAt } : null;
  }
}

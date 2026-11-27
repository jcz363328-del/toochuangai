/** Return the calendar date in the dashboard's business timezone. */
export function localDateKey(timezone = "Asia/Shanghai", now = new Date()) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const year = parts.find((part) => part.type === "year")?.value;
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  return `${year}-${month}-${day}`;
}

/**
 * Find the next local calendar boundary without assuming the host timezone.
 * A minute resolution is intentional: it prevents DST/locale arithmetic from
 * shifting a refresh into the previous business day, while keeping the timer
 * inexpensive and bounded.
 */
export function delayUntilNextLocalDay(timezone = "Asia/Shanghai", now = new Date()) {
  const today = localDateKey(timezone, now);
  const start = now.getTime();
  const max = start + 48 * 60 * 60 * 1000;
  for (let probe = start + 60_000; probe <= max; probe += 60_000) {
    if (localDateKey(timezone, new Date(probe)) !== today) return probe - start;
  }
  // This is only reachable for a broken timezone implementation. Keep a
  // bounded fallback rather than creating a tight timer loop.
  return 24 * 60 * 60 * 1000;
}

/**
 * Schedule one refresh immediately after each local midnight. The timer is
 * unref'ed when supported so it never prevents a clean API shutdown.
 */
export function createDailyRefreshScheduler({
  timezone = "Asia/Shanghai",
  refresh,
  now = () => new Date(),
  setTimer = (callback, delay) => setTimeout(callback, delay),
} = {}) {
  if (typeof refresh !== "function") throw new TypeError("refresh must be a function");
  let timer = null;
  let stopped = true;

  const schedule = () => {
    if (stopped) return;
    const delay = delayUntilNextLocalDay(timezone, now());
    timer = setTimer(async () => {
      timer = null;
      if (stopped) return;
      try {
        await refresh();
      } catch {
        // The dashboard request path still has stale/snapshot fallback. A
        // transient midnight failure must not terminate the API process.
      } finally {
        schedule();
      }
    }, delay);
    timer?.unref?.();
  };

  return {
    start() {
      if (!stopped) return;
      stopped = false;
      schedule();
    },
    stop() {
      stopped = true;
      if (timer != null) clearTimeout(timer);
      timer = null;
    },
    get active() {
      return !stopped;
    },
  };
}


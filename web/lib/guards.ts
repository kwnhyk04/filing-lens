// Request guards: the sign-in redirect target, the same-origin rule, the sign-in limiter.

/** The `next=` path if it stays on `origin` (any origin works: only the path is kept), else null. */
export function safeNext(next: string | null | undefined, origin = "http://web.invalid"): string | null {
  if (!next?.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return null;
  const url = new URL(next, origin); // drops tabs and newlines, resolves dot segments
  if (url.origin !== origin || url.pathname.startsWith("//")) return null;
  return url.pathname + url.search + url.hash;
}

/** A browser request from the web's own pages: Sec-Fetch-Site, else an Origin on the Host asked. */
export function isSameOrigin(headers: Headers): boolean {
  if (headers.get("sec-fetch-site") === "same-origin") return true;
  const origin = headers.get("origin") ?? "";
  // Host, not the request URL: Next builds a route handler's URL on localhost.
  return URL.canParse(origin) && new URL(origin).host === headers.get("host");
}

// ponytail: per-process memory, so each Vercel instance counts alone; step 10's firewall rule covers it.
export function createLimiter({ max = 5, windowMs = 15 * 60_000, now = Date.now } = {}) {
  const failures = new Map<string, number[]>();
  const recent = (key: string) => {
    const kept = (failures.get(key) ?? []).filter((at) => now() - at < windowMs);
    if (kept.length) failures.set(key, kept);
    else failures.delete(key);
    return kept;
  };
  return {
    /**
     * Seconds the key must wait, else 0, and then the attempt counts at once: parallel attempts
     * cannot all pass before any of them fails. A success calls `reset`.
     */
    attempt(key: string): number {
      const kept = recent(key);
      if (kept.length >= max) return Math.ceil((kept[0] + windowMs - now()) / 1000);
      failures.set(key, [...kept, now()]);
      return 0;
    },
    reset(key: string): void {
      failures.delete(key);
    },
  };
}

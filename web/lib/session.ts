// Stateless sessions: `v1.<expiry>.<mac>`, the MAC an HMAC-SHA256 of `v1.<expiry>` (unix seconds).
import { createHmac, timingSafeEqual } from "node:crypto";

import { MIN_SECRET } from "./settings.ts";

export const SESSION_COOKIE = "__Host-filinglens_session";
export const SESSION_TTL_S = 8 * 60 * 60;

function mac(secret: string, payload: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

export function signSession(secret: string, nowMs: number): string {
  const payload = `v1.${Math.floor(nowMs / 1000) + SESSION_TTL_S}`;
  return `${payload}.${mac(secret, payload)}`;
}

export function verifySession(token: string | undefined, secret: string | undefined, nowMs: number): boolean {
  // A missing or short secret signs no one in, since anyone can compute an empty key's MAC.
  if (!secret || secret.length < MIN_SECRET) return false;
  const parts = token?.split(".") ?? [];
  if (parts.length !== 3 || parts[0] !== "v1" || !/^\d{1,12}$/.test(parts[1])) return false;
  // The encoded strings are compared, so a MAC that decodes to the same bytes still fails.
  const given = Buffer.from(parts[2]);
  const expected = Buffer.from(mac(secret, `v1.${parts[1]}`));
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return false;
  return Number(parts[1]) * 1000 > nowMs;
}

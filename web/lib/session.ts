// Stateless sessions: `v2.<sid>.<expiry>.<mac>`, the MAC an HMAC-SHA256 of `v2.<sid>.<expiry>` (unix
// seconds). The sid, 16 random bytes in base64url, keeps each sign-in's recent answers its own.
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

import { MIN_SECRET } from "./settings.ts";

export const SESSION_COOKIE = "__Host-filinglens_session";
export const SESSION_TTL_S = 8 * 60 * 60;
const SID = /^[A-Za-z0-9_-]{22}$/;

function mac(secret: string, payload: string): string {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

export function signSession(secret: string, nowMs: number, sid = randomBytes(16).toString("base64url")): string {
  const payload = `v2.${sid}.${Math.floor(nowMs / 1000) + SESSION_TTL_S}`;
  return `${payload}.${mac(secret, payload)}`;
}

/** The sign-in's id when the token is genuine and unexpired, else null. A v1 token has no id, so it signs no one in. */
export function readSession(token: string | undefined, secret: string | undefined, nowMs: number): { sid: string } | null {
  // A missing or short secret signs no one in, since anyone can compute an empty key's MAC.
  if (!secret || secret.length < MIN_SECRET) return null;
  const parts = token?.split(".") ?? [];
  if (parts.length !== 4 || parts[0] !== "v2" || !SID.test(parts[1]) || !/^\d{1,12}$/.test(parts[2])) return null;
  // The encoded strings are compared, so a MAC that decodes to the same bytes still fails.
  const given = Buffer.from(parts[3]);
  const expected = Buffer.from(mac(secret, `v2.${parts[1]}.${parts[2]}`));
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) return null;
  return Number(parts[2]) * 1000 > nowMs ? { sid: parts[1] } : null;
}

export function verifySession(token: string | undefined, secret: string | undefined, nowMs: number): boolean {
  return readSession(token, secret, nowMs) !== null;
}

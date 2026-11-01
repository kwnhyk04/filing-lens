// Session tokens under `node --test`.
import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";

import { readSession, SESSION_TTL_S, signSession, verifySession } from "./session.ts";
import { MIN_SECRET } from "./settings.ts";

const SECRET = "s".repeat(32);
const NOW = Date.UTC(2026, 9, 19, 12);
const token = signSession(SECRET, NOW);

test("a fresh token holds until it expires, 8 hours on", () => {
  assert.match(token, /^v2\.[A-Za-z0-9_-]{22}\.\d+\.[A-Za-z0-9_-]{43}$/);
  assert.equal(verifySession(token, SECRET, NOW), true);
  assert.equal(verifySession(token, SECRET, NOW + SESSION_TTL_S * 1000 - 1000), true);
  assert.equal(verifySession(token, SECRET, NOW + SESSION_TTL_S * 1000), false);
});

test("each sign-in gets its own id, even two in the same second, and reading the token gives it back", () => {
  const ids = [signSession(SECRET, NOW), signSession(SECRET, NOW)].map((one) => readSession(one, SECRET, NOW)?.sid);
  assert.equal(new Set(ids).size, 2);
  assert.deepEqual(readSession(signSession(SECRET, NOW, "A".repeat(22)), SECRET, NOW), { sid: "A".repeat(22) });
});

const [, sid, expiry, mac] = token.split(".");
const v1Payload = `v1.${expiry}`; // the token before sign-ins had ids, with a genuine MAC
const v1 = `${v1Payload}.${createHmac("sha256", SECRET).update(v1Payload).digest("base64url")}`;
const BAD: [string, string | undefined][] = [
  ["no cookie", undefined],
  ["an empty cookie", ""],
  ["a later expiry", `v2.${sid}.${Number(expiry) + 3600}.${mac}`],
  ["another sign-in's id", `v2.${"B".repeat(22)}.${expiry}.${mac}`],
  ["a genuine v1 token", v1],
  ["another version", `v3.${sid}.${expiry}.${mac}`],
  ["a short id", `v2.${sid.slice(1)}.${expiry}.${mac}`],
  ["a truncated MAC", `v2.${sid}.${expiry}.${mac.slice(0, -1)}`],
  ["an oversized MAC", `v2.${sid}.${expiry}.${mac}A`],
  ["a flipped MAC character", `v2.${sid}.${expiry}.${mac.slice(0, -1)}${mac.endsWith("A") ? "B" : "A"}`],
  ["an extra part", `${token}.x`],
  ["a non-numeric expiry", `v2.${sid}.1e9.${mac}`],
];

for (const [name, value] of BAD) {
  test(`refuses ${name}`, () => {
    assert.equal(verifySession(value, SECRET, NOW), false);
    assert.equal(readSession(value, SECRET, NOW), null);
  });
}

test("refuses a token signed with another secret", () => {
  assert.equal(verifySession(token, "t".repeat(32), NOW), false);
});

test("a missing secret, or one shorter than the startup check's minimum, signs no one in", () => {
  for (const secret of ["", "s".repeat(MIN_SECRET - 1)]) {
    assert.equal(verifySession(signSession(secret, NOW), secret, NOW), false);
  }
  assert.equal(verifySession(signSession("", NOW), undefined, NOW), false);
});

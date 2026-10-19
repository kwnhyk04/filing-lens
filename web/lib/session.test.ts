// Session tokens under `node --test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { SESSION_TTL_S, signSession, verifySession } from "./session.ts";
import { MIN_SECRET } from "./settings.ts";

const SECRET = "s".repeat(32);
const NOW = Date.UTC(2026, 9, 19, 12);
const token = signSession(SECRET, NOW);

test("a fresh token holds until it expires, 8 hours on", () => {
  assert.match(token, /^v1\.\d+\.[A-Za-z0-9_-]{43}$/);
  assert.equal(verifySession(token, SECRET, NOW), true);
  assert.equal(verifySession(token, SECRET, NOW + SESSION_TTL_S * 1000 - 1000), true);
  assert.equal(verifySession(token, SECRET, NOW + SESSION_TTL_S * 1000), false);
});

const [, expiry, mac] = token.split(".");
const BAD: [string, string | undefined][] = [
  ["no cookie", undefined],
  ["an empty cookie", ""],
  ["a later expiry", `v1.${Number(expiry) + 3600}.${mac}`],
  ["another version", `v2.${expiry}.${mac}`],
  ["a truncated MAC", `v1.${expiry}.${mac.slice(0, -1)}`],
  ["an oversized MAC", `v1.${expiry}.${mac}A`],
  ["a flipped MAC character", `v1.${expiry}.${mac.slice(0, -1)}${mac.endsWith("A") ? "B" : "A"}`],
  ["an extra part", `${token}.x`],
  ["a non-numeric expiry", `v1.1e9.${mac}`],
];

for (const [name, value] of BAD) {
  test(`refuses ${name}`, () => {
    assert.equal(verifySession(value, SECRET, NOW), false);
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

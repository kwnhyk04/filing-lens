// The sign-in and BFF guards under `node --test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { createLimiter, isSameOrigin, safeNext } from "./guards.ts";

const ORIGIN = "http://127.0.0.1:3100";

test("next= keeps a path on the web's origin", () => {
  assert.equal(safeNext("/coverage?after=x", ORIGIN), "/coverage?after=x");
  assert.equal(safeNext("/", ORIGIN), "/");
});

const LEAVING = [
  "//evil.example",
  "https://evil.example/",
  "/\\evil.example",
  "/\\t/evil.example",
  "/\t/evil.example",
  "/x/..//evil.example",
  "coverage",
  "",
  null,
];

for (const next of LEAVING) {
  test(`next= refuses ${JSON.stringify(next)}`, () => {
    assert.equal(safeNext(next, ORIGIN), null);
  });
}

// Next builds a route handler's URL on localhost, so the rule compares Origin with Host.
const HOST = { Host: "127.0.0.1:3100" };
const ORIGINS: [string, Record<string, string>, boolean][] = [
  ["no header", HOST, false],
  ["Origin: null", { ...HOST, Origin: "null" }, false],
  ["another port", { ...HOST, Origin: "http://127.0.0.1:3101" }, false],
  ["another host", { ...HOST, Origin: "http://localhost:3100" }, false],
  ["no Host", { Origin: ORIGIN }, false],
  ["a cross-site fetch", { ...HOST, "Sec-Fetch-Site": "cross-site" }, false],
  ["the same origin", { ...HOST, Origin: ORIGIN }, true],
  ["Sec-Fetch-Site: same-origin", { "Sec-Fetch-Site": "same-origin" }, true],
];

for (const [name, headers, expected] of ORIGINS) {
  test(`the origin rule with ${name}: ${expected ? "passes" : "refused"}`, () => {
    assert.equal(isSameOrigin(new Headers(headers)), expected);
  });
}

test("the limiter locks a key after 5 attempts in 15 minutes, until the first expires", () => {
  let now = 0;
  const limiter = createLimiter({ now: () => now });
  for (let i = 0; i < 5; i++) {
    assert.equal(limiter.attempt("a"), 0);
    now += 60_000;
  }
  assert.equal(limiter.attempt("a"), 10 * 60, "the first attempt clears 15 minutes after it");
  assert.equal(limiter.attempt("b"), 0, "keys are separate");
  now = 15 * 60_000;
  assert.equal(limiter.attempt("a"), 0);
});

test("attempts are counted as they start, so parallel ones cannot pass together", () => {
  const limiter = createLimiter({ now: () => 0 });
  const waits = Array.from({ length: 10 }, () => limiter.attempt("a"));
  assert.deepEqual(waits.map((wait) => wait === 0), [true, true, true, true, true, false, false, false, false, false]);
});

test("a success clears a key's attempts", () => {
  const limiter = createLimiter({ now: () => 0 });
  for (let i = 0; i < 5; i++) limiter.attempt("a");
  limiter.reset("a");
  assert.equal(limiter.attempt("a"), 0);
});

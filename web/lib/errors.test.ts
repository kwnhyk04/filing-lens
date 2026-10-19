// Failure classification under `node --test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { ApiError } from "../../clients/ts/index.ts";
import { classify, failureLabel } from "./errors.ts";

const CASES: [string, unknown, ReturnType<typeof classify>][] = [
  ["a network error", new TypeError("fetch failed"), { kind: "offline" }],
  ["a timeout", new DOMException("timed out", "TimeoutError"), { kind: "offline" }],
  ["a proxy's 502 page", new ApiError(502, "unexpected_response", "HTTP 502"), { kind: "offline" }],
  ["a 500 internal", new ApiError(500, "internal", "HTTP 500", undefined, "r1"), { kind: "offline" }],
  ["a GraphQL internal (HTTP 200)", new ApiError(200, "internal", "Unexpected error."), { kind: "offline" }],
  ["a 401", new ApiError(401, "unauthorized", "No key.", undefined, "r2"), { kind: "misconfigured", requestId: "r2" }],
  ["a 403", new ApiError(403, "forbidden", "Admin only.", undefined, "r3"), { kind: "misconfigured", requestId: "r3" }],
  [
    "a 503 with Retry-After",
    new ApiError(503, "overloaded", "Too many answers in progress.", 2, "r4"),
    { kind: "problem", status: 503, code: "overloaded", detail: "Too many answers in progress.", retryAfterS: 2, requestId: "r4" },
  ],
  [
    "a 503 without Retry-After",
    new ApiError(503, "ai_unavailable", "AI is switched off.", undefined, "r5"),
    { kind: "problem", status: 503, code: "ai_unavailable", detail: "AI is switched off.", retryAfterS: undefined, requestId: "r5" },
  ],
  [
    "a 429",
    new ApiError(429, "rate_limited", "Slow down.", 7, "r6"),
    { kind: "problem", status: 429, code: "rate_limited", detail: "Slow down.", retryAfterS: 7, requestId: "r6" },
  ],
];

for (const [name, error, expected] of CASES) {
  test(`${name} is ${expected.kind}`, () => {
    assert.deepEqual(classify(error), expected);
  });
}

test("a browser that left is logged as client_aborted at info; a stalled or unreachable API stays offline at warn", () => {
  // Next aborts a route's request.signal with an Error named ResponseAborted when the browser disconnects.
  const left = [new DOMException("The operation was aborted.", "AbortError"), Object.assign(new Error("aborted"), { name: "ResponseAborted" })];
  for (const error of left) assert.deepEqual(failureLabel(error, classify(error)), { label: "client_aborted", level: "info" });
  for (const error of [new DOMException("timed out", "TimeoutError"), new TypeError("fetch failed")]) {
    assert.deepEqual(failureLabel(error, classify(error)), { label: "offline", level: "warn" });
  }
});

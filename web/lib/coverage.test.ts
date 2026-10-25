// The header's coverage line under `node --test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { coverageLine } from "./coverage.ts";

test("the line counts companies and filings, singular when one, with + when more exist", () => {
  assert.equal(coverageLine(30, 30), "30 companies · 30 filings");
  assert.equal(coverageLine(1, 1), "1 company · 1 filing");
  assert.equal(coverageLine(30, 30, true), "30 companies · 30+ filings");
});

// `node scripts/favicon.mjs` under `node --test`: app/favicon.ico is what it draws from lib/logo.ts, so the file
// never drifts from the mark.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { favicon } from "./favicon.mjs";

test("app/favicon.ico is the app icon drawn from the mark at 16, 32 and 48 px, each a PNG", async () => {
  const drawn = await favicon();
  const saved = readFileSync(new URL("../app/favicon.ico", import.meta.url));
  assert.ok(saved.equals(drawn), "app/favicon.ico is not what the mark draws now: run node scripts/favicon.mjs");
  assert.deepEqual([drawn.readUInt16LE(0), drawn.readUInt16LE(2), drawn.readUInt16LE(4)], [0, 1, 3]);
  for (const [i, side] of [16, 32, 48].entries()) {
    const entry = 6 + 16 * i;
    assert.deepEqual([drawn[entry], drawn[entry + 1]], [side, side]);
    const png = drawn.subarray(drawn.readUInt32LE(entry + 12), drawn.readUInt32LE(entry + 12) + drawn.readUInt32LE(entry + 8));
    assert.equal(png.subarray(1, 4).toString(), "PNG");
    assert.deepEqual([png.readUInt32BE(16), png.readUInt32BE(20)], [side, side]);
  }
});

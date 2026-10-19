// `npm run session-secret` under `node --test`, on a temporary .env.
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const SCRIPT = fileURLToPath(new URL("./session-secret.mjs", import.meta.url));

test("appends 32 random bytes as hex and prints nothing; a second run refuses", () => {
  const env = join(mkdtempSync(join(tmpdir(), "session-secret-")), ".env");
  writeFileSync(env, "API_URL=http://127.0.0.1:4100");
  const output = execFileSync(process.execPath, [SCRIPT, env], { encoding: "utf8" });
  assert.equal(output, "");
  const text = readFileSync(env, "utf8");
  assert.match(text, /^API_URL=http:\/\/127\.0\.0\.1:4100\nSESSION_SECRET=[0-9a-f]{64}\n$/);

  const again = spawnSync(process.execPath, [SCRIPT, env], { encoding: "utf8" });
  assert.equal(again.status, 1);
  assert.equal(again.stdout, "");
  assert.match(again.stderr, /already in \.env/);
  assert.ok(!again.stderr.includes(text.split("=").at(-1).trim()), "the secret is never printed");
  assert.equal(readFileSync(env, "utf8"), text);
});

test("creates .env when it is missing", () => {
  const env = join(mkdtempSync(join(tmpdir(), "session-secret-")), ".env");
  execFileSync(process.execPath, [SCRIPT, env]);
  assert.match(readFileSync(env, "utf8"), /^SESSION_SECRET=[0-9a-f]{64}\n$/);
});

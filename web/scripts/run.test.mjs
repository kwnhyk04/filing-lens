// The launcher's environment under `node --test`; nothing is started.
import assert from "node:assert/strict";
import { test } from "node:test";

import { webEnv } from "./run.mjs";

const DOTENV = [
  "API_URL=http://127.0.0.1:4100",
  "API_KEY=from-the-file",
  "ADMIN_API_KEY=never-passed",
  "POSTGRES_PASSWORD=not-the-webs",
  "LOGIN_PASSWORD_HASH='$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA'",
  "SESSION_SECRET=${API_KEY}",
].join("\n");

test("the web's keys come from .env, and a real environment variable wins", () => {
  const env = webEnv({ API_KEY: "from-the-environment", PATH: "/bin" }, DOTENV);
  assert.equal(env.API_KEY, "from-the-environment");
  assert.equal(env.API_URL, "http://127.0.0.1:4100");
  assert.equal(env.PATH, "/bin");
});

test("values are literal: single quotes keep $, and ${} is not expanded", () => {
  const env = webEnv({}, DOTENV);
  assert.equal(env.LOGIN_PASSWORD_HASH, "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA");
  assert.equal(env.SESSION_SECRET, "${API_KEY}");
});

test("only the web's keys come from .env, and ADMIN_API_KEY is never passed", () => {
  const env = webEnv({ ADMIN_API_KEY: "inherited" }, DOTENV);
  assert.equal(env.POSTGRES_PASSWORD, undefined);
  assert.equal("ADMIN_API_KEY" in env, false);
});

test("a missing .env is fine", () => {
  assert.deepEqual(webEnv({ API_URL: "http://api.test" }, undefined), { API_URL: "http://api.test" });
});

// The web's startup settings under `node --test`.
import assert from "node:assert/strict";
import { test } from "node:test";

import { loadSettings } from "./settings.ts";

const HASH = "$argon2id$v=19$m=65536,t=2,p=1$c29tZXNhbHQ$CTFhFdXPJO1aFaMaO6Mm5c8y7cJHAph8ArZWb2GRPPc";
const GOOD = {
  API_URL: "http://127.0.0.1:4100",
  API_KEY: "a".repeat(32),
  SESSION_SECRET: "s".repeat(32),
  LOGIN_PASSWORD_HASH: HASH,
};

test("good settings load", () => {
  assert.deepEqual(loadSettings(GOOD), {
    apiUrl: GOOD.API_URL,
    apiKey: GOOD.API_KEY,
    sessionSecret: GOOD.SESSION_SECRET,
    passwordHash: HASH,
  });
});

test("every missing variable is named in one error", () => {
  assert.throws(
    () => loadSettings({}),
    {
      message:
        "Invalid configuration: API_URL: required; API_KEY: required; SESSION_SECRET: required;" +
        " LOGIN_PASSWORD_HASH: required",
    },
  );
});

const BAD: [string, Record<string, string>, RegExp][] = [
  ["a URL without http", { API_URL: "127.0.0.1:4100" }, /API_URL: an http\(s\) URL/],
  ["a short API key", { API_KEY: "x".repeat(31) }, /API_KEY: at least 32 characters/],
  ["a short session secret", { SESSION_SECRET: "x".repeat(31) }, /SESSION_SECRET: at least 32/],
  ["a weak hash", { LOGIN_PASSWORD_HASH: HASH.replace("m=65536", "m=1024") }, /LOGIN_PASSWORD_HASH: not an argon2id/],
];

for (const [name, change, expected] of BAD) {
  test(`${name} is refused by name, never by value`, () => {
    const env = { ...GOOD, ...change };
    assert.throws(() => loadSettings(env), (error: Error) => {
      assert.match(error.message, expected);
      for (const value of Object.values(change)) assert.ok(!error.message.includes(value));
      return true;
    });
  });
}

// The theme cookie under `node --test`: what the root layout reads and what the header's toggle writes.
import assert from "node:assert/strict";
import { test } from "node:test";

import { appearance, THEME_COOKIE, themeCookie, themeOf } from "./theme.ts";

test("a cookie that says neither light nor dark means the system's theme", () => {
  assert.equal(themeOf("light"), "light");
  assert.equal(themeOf("dark"), "dark");
  for (const value of [undefined, "", "system", "Dark", "blue", "light; dark"]) assert.equal(themeOf(value), "system");
});

test("Light and Dark are kept for a year on the whole site; System deletes the cookie", () => {
  assert.equal(THEME_COOKIE, "fl-theme");
  assert.equal(themeCookie("dark", true), "fl-theme=dark; Max-Age=31536000; Path=/; SameSite=Lax; Secure");
  assert.equal(themeCookie("light", false), "fl-theme=light; Max-Age=31536000; Path=/; SameSite=Lax");
  assert.equal(themeCookie("system", true), "fl-theme=; Max-Age=0; Path=/; SameSite=Lax; Secure");
});

test("the page looks like the theme picked, or like the system when that is System", () => {
  assert.equal(appearance("light", true), "light");
  assert.equal(appearance("dark", false), "dark");
  assert.equal(appearance("system", true), "dark");
  assert.equal(appearance("system", false), "light");
});

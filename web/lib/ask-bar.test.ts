// The Ask bar on the landing hero and on Ask: one set of neutral greys, no green, and WCAG AA in both themes.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

const sheet = (path: string) => readFileSync(new URL(`../${path}`, import.meta.url), "utf8");
const globals = sheet("app/globals.css");

/** A token's light and dark colours, through any var() in :root. */
function token(name: string): [string, string] {
  const value = new RegExp(`^\\s*${name}:\\s*(.+);$`, "m").exec(globals)?.[1];
  assert.ok(value, `${name} is not set`);
  const alias = /^var\((--[\w-]+)\)$/.exec(value);
  if (alias) return token(alias[1]);
  const pair = /^light-dark\((#\w{6}), (#\w{6})\)$/.exec(value);
  assert.ok(pair, `${name} is not a light and dark pair: ${value}`);
  return [pair[1], pair[2]];
}

const channels = (hex: string) => [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16));

function luminance(hex: string): number {
  const [r, g, b] = channels(hex).map((value) => {
    const unit = value / 255;
    return unit <= 0.04045 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(one: string, other: string): number {
  const [low, high] = [luminance(one), luminance(other)].sort((a, b) => a - b);
  return (high + 0.05) / (low + 0.05);
}

const THEMES = [0, 1] as const; // light, dark
// What the focus ring sits on: the stage's ground and its two glows (ask.css, the dark teal glow over the ground).
const GROUND = [
  ["#faf8f3", "#bdebe1", "#d6e0ec"],
  ["#0f1b2d", "#134146", "#13283c"],
];

test("the bar's colours are greys: no channel stands out, as green does", () => {
  for (const name of ["--bar", "--bar-ink", "--bar-hint", "--bar-line", "--bar-send", "--on-bar-send"]) {
    for (const color of token(name)) {
      const values = channels(color);
      assert.ok(Math.max(...values) - Math.min(...values) <= 10, `${name} ${color}`);
    }
  }
});

test("text, placeholder and the button's arrow reach 4.5:1 in both themes", () => {
  for (const theme of THEMES) {
    const bar = token("--bar")[theme];
    assert.ok(contrast(token("--bar-ink")[theme], bar) >= 4.5, "text");
    assert.ok(contrast(token("--bar-hint")[theme], bar) >= 4.5, "placeholder");
    assert.ok(contrast(token("--on-bar-send")[theme], token("--bar-send")[theme]) >= 4.5, "arrow");
  }
});

test("the button, the hairline and the focus ring reach 3:1 against what they sit on, in both themes", () => {
  for (const theme of THEMES) {
    const bar = token("--bar")[theme];
    assert.ok(contrast(token("--bar-send")[theme], bar) >= 3, "button");
    assert.ok(contrast(token("--bar-line")[theme], bar) >= 3, "hairline");
    for (const ground of GROUND[theme]) assert.ok(contrast(token("--bar-send")[theme], ground) >= 3, `ring on ${ground}`);
  }
});

/** The declarations of each rule in `css` whose selector is exactly `selector`. */
function rule(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = [...css.matchAll(new RegExp(`^${escaped} \\{([^}]*)\\}`, "gm"))].map((match) => match[1]);
  assert.ok(found.length, `no rule for ${selector}`);
  return found.join("");
}

const BARS: [string, string[]][] = [
  ["app/ask/ask.css", [".stage-input", ".stage-input:has(textarea:focus-visible)", ".stage-input textarea", ".stage-input textarea::placeholder", ".stage-send", ".stage-send:hover", ".stage-send:focus-visible"]],
  ["components/hero-live.css", [".pb-capsule", ".pb-capsule::before", ".pb-send"]],
];

test("both bars take their colours from those tokens, and no green or hero colour is left in them", () => {
  for (const [path, selectors] of BARS) {
    const css = sheet(path);
    for (const selector of selectors) {
      const declarations = rule(css, selector);
      assert.match(declarations, /var\(--(on-)?bar/, selector);
      assert.doesNotMatch(declarations, /--accent|--tint|--hero-|--on-body|--glass|--field|45 212 191/, selector);
    }
  }
});

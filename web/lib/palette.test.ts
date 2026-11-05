// The site's one palette (docs/design.md): cool greys and a steel accent, green, red and amber only on the tokens
// that carry meaning, WCAG AA in both themes, and one set of tokens for the hero, Ask and both Ask bars.
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
  if (/^#\w{6}$/.test(value)) return [value, value];
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
const SOLID = ["--paper", "--sheet", "--sunk"];
const SURFACES = [...SOLID, "--tint"];
const TEXT = [
  ...["--ink", "--ink-2", "--ink-3", "--accent"].flatMap((ink) => SURFACES.map((ground) => [ink, ground])),
  ["--on-accent", "--accent"],
  ["--on-mark", "--mark"],
  ["--note-ink", "--note-bg"],
  ["--bad-ink", "--bad-bg"],
  ["--ok", "--ok-bg"],
  ["--ok", "--sheet"],
  ["--ok", "--sunk"],
  ["--bar-ink", "--bar"],
  ["--bar-hint", "--bar"],
  ["--on-bar-send", "--bar-send"],
];
const GRAPHICS = [
  ...["--field", "--accent"].flatMap((line) => SOLID.map((ground) => [line, ground])),
  ["--accent", "--tint"],
  ["--accent", "--glow"], // a focus ring on the hero's and the stage's ground
  ["--accent", "--deep"],
  ["--bar-send", "--bar"],
  ["--bar-line", "--bar"],
  ["--mark-line", "--mark"],
  ["--ok-fill", "--sheet"],
  ["--ok-fill", "--sunk"],
];

function reach(pairs: string[][], least: number) {
  for (const theme of THEMES) {
    for (const [ink, ground] of pairs) {
      const ratio = contrast(token(ink)[theme], token(ground)[theme]);
      assert.ok(ratio >= least, `${ink} on ${ground}, ${theme ? "dark" : "light"}: ${ratio.toFixed(2)}`);
    }
  }
}

test("text, placeholders and the buttons' labels reach 4.5:1 in both themes", () => reach(TEXT, 4.5));

test("field borders, focus rings, the send button and the check's badge reach 3:1 in both themes", () => reach(GRAPHICS, 3));

test("the white tick on the passed check's badge reaches 4.5:1", () => {
  assert.ok(contrast("#ffffff", token("--ok-fill")[0]) >= 4.5);
  assert.match(sheet("components/hero-live.css"), /background: var\(--ok-fill\)\s+url\([^)]*stroke='white'/);
});

// What may leave the greys, each for what it means: the highlighter, caution, errors and passed checks.
const MEANING = /^\s*--(on-)?(mark|note|bad|ok)\b/;
const FILES = [
  "app/globals.css",
  "app/landing.css",
  "app/ask/ask.css",
  "components/hero-live.css",
  "components/bond.css",
  "components/bond.tsx",
  "components/hero-field.tsx",
  "lib/logo.ts",
  "app/icon.svg",
];

/** Every colour written in a line, as its channels: hex, in a data URI too, and rgb(). */
function colours(line: string): number[][] {
  const hex = [...line.matchAll(/(?:#|%23)([0-9a-f]{6})\b/gi)].map((match) => channels(`#${match[1]}`));
  const rgb = [...line.matchAll(/rgb\((\d+)[, ]+(\d+)[, ]+(\d+)/g)].map((match) => match.slice(1, 4).map(Number));
  return [...hex, ...rgb];
}

test("every colour outside those tokens is a cool grey: nothing green, teal, navy or warm", () => {
  for (const path of FILES) {
    for (const [i, line] of sheet(path).split("\n").entries()) {
      if (MEANING.test(line)) continue;
      for (const [r, g, b] of colours(line)) assert.ok(r <= g && g <= b && b - r <= 25, `${path}:${i + 1} rgb(${r} ${g} ${b})`);
    }
  }
});

test("green, red and amber stay muted on the dark background", () => {
  for (const line of globals.split("\n").filter((each) => MEANING.test(each))) {
    const name = /--[\w-]+/.exec(line)![0];
    const [low, high] = [Math.min(...channels(token(name)[1])), Math.max(...channels(token(name)[1]))].map((value) => value / 255);
    const saturation = (high - low) / (1 - Math.abs(high + low - 1));
    assert.ok(saturation <= 0.6, `${name}: ${saturation.toFixed(2)}`);
  }
});

test("the hero, Ask and the moving story keep no palette of their own", () => {
  for (const path of FILES.filter((each) => each.endsWith(".css"))) assert.doesNotMatch(sheet(path), /--hero-|--on-body/, path);
});

/** The declarations of each rule in `css` whose selector is exactly `selector`. */
function rule(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const found = [...css.matchAll(new RegExp(`^${escaped} \\{([^}]*)\\}`, "gm"))].map((match) => match[1]);
  assert.ok(found.length, `no rule for ${selector}`);
  return found.join("");
}

const BARS: [string, string[]][] = [
  ["app/ask/ask.css", [".stage-input", ".stage-input textarea", ".stage-input textarea::placeholder", ".stage-send", ".stage-send:hover"]],
  ["components/hero-live.css", [".pb-capsule", ".pb-capsule::before", ".pb-send"]],
];

test("both bars take their colours from the bar's tokens", () => {
  for (const [path, selectors] of BARS) {
    const css = sheet(path);
    for (const selector of selectors) {
      const declarations = rule(css, selector);
      assert.match(declarations, /var\(--(on-)?bar/, selector);
      assert.doesNotMatch(declarations, /--accent|--tint|--glass|--field/, selector);
    }
  }
});

test("the story's active pager dot is the accent", () => {
  assert.match(rule(sheet("components/hero-live.css"), '.pb-progress [data-current="true"]'), /background: var\(--accent\)/);
});

test("every focus ring is the accent, the Ask bar's and its send button's included", () => {
  assert.match(rule(globals, ":focus-visible"), /outline: 3px solid var\(--accent\)/);
  assert.match(rule(sheet("app/ask/ask.css"), ".stage-input:has(textarea:focus-visible)"), /outline: 3px solid var\(--accent\)/);
  assert.doesNotMatch(sheet("app/ask/ask.css"), /\.stage-send:focus-visible/);
});

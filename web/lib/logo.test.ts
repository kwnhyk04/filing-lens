// The mark under `node --test`: its geometry rules, and every copy of it in the repo kept identical to
// lib/logo.ts (the CSS, the favicon and the files in docs/brand).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { COLORS, faviconSvg, GAP, HALF, INK_PATH, markSvg, POINTS, RADIUS, STROKE, TEAL_PATH } from "./logo.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8").trim();
const distance = (a: { x: number; y: number }, b: { x: number; y: number }) => Math.hypot(a.x - b.x, a.y - b.y);

test("the arcs sit on one circle and clear the bar by the gap", () => {
  const { arcEnd } = POINTS;
  assert.ok(Math.abs(distance(arcEnd, { x: 0, y: 0 }) - RADIUS) < 0.001);
  // From the centre of an arc's round end to the bar's centre line: half a stroke, the gap, half a stroke.
  assert.equal(arcEnd.y - STROKE, GAP);
});

test("the bar breaks where the circle crosses it, with the same gap on both sides", () => {
  const { tealEnd, inkStart, inkEnd } = POINTS;
  assert.equal(inkStart - tealEnd - STROKE, GAP);
  assert.equal((tealEnd + inkStart) / 2, RADIUS);
  // No two strokes come closer than the gap, the arcs' ends and the teal's ends included.
  assert.ok(distance(POINTS.arcEnd, { x: tealEnd, y: 0 }) - STROKE >= GAP - 0.01);
  // The ink sticks out past the lens's outer edge by more than a stroke on each side.
  assert.ok(inkEnd + STROKE / 2 - (RADIUS + STROKE / 2) > STROKE);
  assert.deepEqual(HALF, { width: inkEnd + STROKE / 2, height: RADIUS + STROKE / 2 });
});

test("the paths draw those points: two arcs and two pills in ink, the bar's middle in teal", () => {
  const { arcEnd, tealEnd, inkStart, inkEnd } = POINTS;
  assert.ok(INK_PATH.includes(`M${-arcEnd.x} ${-arcEnd.y}A${RADIUS} ${RADIUS} 0 0 1 ${arcEnd.x} ${-arcEnd.y}`));
  assert.ok(INK_PATH.includes(`M${arcEnd.x} ${arcEnd.y}A${RADIUS} ${RADIUS} 0 0 1 ${-arcEnd.x} ${arcEnd.y}`));
  assert.ok(INK_PATH.includes(`M${-inkEnd} 0H${-inkStart}M${inkStart} 0H${inkEnd}`));
  assert.equal(TEAL_PATH, `M${-tealEnd} 0H${tealEnd}`);
  const svg = markSvg(COLORS.light);
  assert.match(svg, /stroke-width="4" stroke-linecap="round"/);
  assert.equal(svg.match(/<path /g)?.length, 2);
});

test("the files in docs/brand are the light, dark and one-colour marks", () => {
  assert.equal(read("../../docs/brand/filinglens-mark-light.svg"), markSvg(COLORS.light));
  assert.equal(read("../../docs/brand/filinglens-mark-dark.svg"), markSvg(COLORS.dark));
  assert.equal(read("../../docs/brand/filinglens-mark-mono.svg"), markSvg({ ink: "currentColor", teal: "currentColor" }));
});

test("the favicon is the square mark, light, and dark in a dark browser", () => {
  assert.equal(read("../app/icon.svg"), faviconSvg());
  assert.match(faviconSvg(), /viewBox="-21.5 -21.5 43 43"/);
  assert.match(faviconSvg(), /@media \(prefers-color-scheme: ?dark\)/);
});

test("the header's and the narrow pages' mark in the CSS is the light mark, and the dark one in dark", () => {
  const css = read("../app/globals.css");
  // `--logo`, since `--mark` is the highlighter; single quotes inside the CSS string stand for double ones.
  const marks = [...css.matchAll(/--logo: url\("data:image\/svg\+xml,([^"]+)"\)/g)].map((m) =>
    decodeURIComponent(m[1]).replaceAll("'", '"'),
  );
  assert.deepEqual([...new Set(marks)].sort(), [markSvg(COLORS.dark), markSvg(COLORS.light)].sort());
});

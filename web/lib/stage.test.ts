// Ask's stage under `node --test`: its phase from what the stream and the sources lookup reported, and what
// floats round it: the covered filings, then each cited source in its filing's place.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { Snapshot } from "./demo.ts";
import {
  ARRIVE_MS,
  citedThings,
  coveredThings,
  landed,
  PULL_MS,
  placeThings,
  revealParts,
  revealTimes,
  SLOTS,
  stagePhase,
  stageView,
  STEP_MS,
} from "./stage.ts";

const snapshot = (): Snapshot =>
  JSON.parse(readFileSync(new URL("../demo/snapshot.json", import.meta.url), "utf8")) as Snapshot;
const saved = (data: Snapshot, id: string) => data.answers.find((item) => item.id === id)!.answer;

test("the phase follows what was reported: reading until the answer and its sources are both in, then done", () => {
  const data = snapshot();
  const x04 = saved(data, "x04"), o02 = saved(data, "o02");
  const state = { asked: "q", answer: null, sources: undefined, sourcesFailed: false, problem: false };
  assert.equal(stagePhase({ ...state, asked: null }), "empty");
  assert.equal(stagePhase(state), "reading");
  assert.equal(stagePhase({ ...state, problem: true }), "failed");
  assert.equal(stagePhase({ ...state, answer: x04 }), "reading"); // checked, but its sources not loaded yet
  assert.equal(stagePhase({ ...state, answer: x04, sources: data.sources }), "done");
  assert.equal(stagePhase({ ...state, answer: x04, sourcesFailed: true }), "done");
  assert.equal(stagePhase({ ...state, answer: o02 }), "done"); // a refusal cites nothing to wait for
});

test("the card's parts come in the hero's order: Read as, the passages, the answer, the check", () => {
  const data = snapshot();
  const x04 = saved(data, "x04"), n01 = saved(data, "n01"), o02 = saved(data, "o02");
  assert.deepEqual(revealParts(x04, landed(x04, data.sources, false)), ["read", "passages", "answer", "check"]);
  assert.deepEqual(revealParts(n01, landed(n01, data.sources, false)), ["read", "passages", "answer", "check"]); // a fact
  assert.deepEqual(revealParts(n01, landed(n01, undefined, true)), ["read", "passages", "answer", "check"]); // its quotes, unnamed
  assert.deepEqual(revealParts(o02, landed(o02, undefined, false)), ["read", "answer"]); // a refusal: no passage, no check
  assert.deepEqual(revealParts({ ...x04, reading: null }, true), ["passages", "answer", "check"]);
  assert.equal(landed(x04, undefined, false), false, "the passages wait for the lookup");
});

test("the reveal settles within 2 s of the data: the pull, then each part a step apart", () => {
  assert.deepEqual(revealTimes(4, true), [PULL_MS, PULL_MS + STEP_MS, PULL_MS + 2 * STEP_MS, PULL_MS + 3 * STEP_MS]);
  assert.deepEqual(revealTimes(2, false), [0, STEP_MS]);
  for (const pull of [true, false]) {
    for (let n = 1; n <= 4; n++) assert.ok(revealTimes(n, pull).at(-1)! + ARRIVE_MS <= 2000, `${n} parts, pull ${pull}`);
  }
});

test("the stage's view: the data's phase, then the pull and the reveal, and the leave over all of them", () => {
  const at = (step: number, pull = true, leaving = false) => ({ step, parts: 4, pull, leaving });
  assert.equal(stageView("empty", at(Infinity)), "empty");
  assert.equal(stageView("reading", at(0)), "reading");
  assert.equal(stageView("failed", at(Infinity)), "failed");
  assert.equal(stageView("done", at(0)), "pulling");
  assert.equal(stageView("done", at(0, false)), "revealing");
  assert.equal(stageView("done", at(2)), "revealing");
  assert.equal(stageView("done", at(4)), "done");
  assert.equal(stageView("done", at(Infinity)), "done");
  assert.equal(stageView("done", at(Infinity, false, true)), "leaving");
  assert.equal(stageView("failed", at(Infinity, false, true)), "leaving");
});

test("covered filings float as their form over their year, at most one fewer than the places", () => {
  const data = snapshot();
  const covered = coveredThings(data.companies);
  assert.equal(covered.length, SLOTS - 1);
  const [first] = data.companies;
  const filing = first.filings.edges[0].node;
  assert.deepEqual(covered[0], {
    kind: "filing",
    title: `${first.ticker} 10-K`,
    sub: `FY${filing.fiscalYear}`,
    icon: "file",
    filing: `${first.ticker} 10-K FY${filing.fiscalYear}`,
  });
  assert.ok(covered.every((thing) => thing.kind === "filing"));
});

test("cited sources are known only once their cards load: a passage by its item, a fact by its value", () => {
  const data = snapshot();
  assert.deepEqual(citedThings(saved(data, "x04")), []);
  assert.deepEqual(citedThings(saved(data, "x04"), data.sources), [
    { kind: "passage", title: "Item 1", sub: "AMZN 10-K FY2025", icon: "file-text", filing: "AMZN 10-K FY2025" },
  ]);
  assert.deepEqual(citedThings(saved(data, "n01"), data.sources), [
    { kind: "fact", title: "416,161,000,000 USD", sub: "AAPL 10-K FY2025", icon: "hash", filing: "AAPL 10-K FY2025" },
  ]);
  assert.deepEqual(citedThings(saved(data, "o02"), data.sources), []);
});

test("each cited source takes its own filing's place, else an empty one, else an uncited filing's from the end", () => {
  const filing = (ticker: string) => ({ kind: "filing" as const, title: `${ticker} 10-K`, sub: "FY2025", icon: "file", filing: `${ticker} 10-K FY2025` });
  const passage = (ticker: string, item: string) => ({ kind: "passage" as const, title: `Item ${item}`, sub: `${ticker} 10-K FY2025`, icon: "file-text", filing: `${ticker} 10-K FY2025` });
  const covered = ["CAT", "LLY", "KO", "WMT"].map(filing);
  // Nothing cited yet: the covered filings in their places, the rest empty, nothing pulled.
  const before = placeThings(covered, []);
  assert.deepEqual(before.env.slice(0, 4), covered);
  assert.equal(before.env.length, SLOTS - 1);
  assert.deepEqual(before.pulls, []);
  // Two passages of LLY's 10-K: the first takes LLY's place, the second the first empty one.
  const lly = placeThings(covered, [passage("LLY", "7"), passage("LLY", "1A")]);
  assert.deepEqual(lly.pulls, [1, 4]);
  assert.deepEqual([lly.env[0], lly.env[1], lly.env[4]], [covered[0], passage("LLY", "7"), passage("LLY", "1A")]);
  // With every place taken, a filing not in the list takes the last uncited filing's place.
  const full = Array.from({ length: SLOTS - 1 }, (_, i) => filing(`T${i}`));
  const aapl = placeThings(full, [passage("AAPL", "8")]);
  assert.deepEqual(aapl.pulls, [SLOTS - 2]);
  assert.equal(aapl.env.filter((thing) => thing?.filing === "AAPL 10-K FY2025").length, 1);
  assert.equal(aapl.env.length, SLOTS - 1);
});

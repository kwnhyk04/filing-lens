// Ask's stage under `node --test`: its phase from what the stream and the sources lookup reported, and what
// floats round it: the covered filings, then each cited source in its filing's place.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { Snapshot } from "./demo.ts";
import {
  CALM_MS,
  calmPace,
  citedThings,
  coveredThings,
  ENTER_MS,
  landed,
  PULL_MS,
  placeThings,
  RELEASE_MS,
  revealParts,
  revealTimes,
  sentences,
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

test("the card's parts come one by one in the hero's order: Read as, each source, the filing tags, the heading, each sentence, the check, the numbers, the notes, the foot", () => {
  const data = snapshot();
  const [n01, x04, c12, x02, o02] = ["n01", "x04", "c12", "x02", "o02"].map((id) => saved(data, id));
  assert.deepEqual(revealParts(n01, data.sources, false), ["read", "source", "filings", "heading", "sentence", "check", "table", "foot"]);
  assert.deepEqual(revealParts(x04, data.sources, false), ["read", "source", "filings", "heading", "sentence", "sentence", "check", "foot"]);
  assert.deepEqual(revealParts(c12, data.sources, false), [
    "read", "source", "source", "source", "source", "filings", "heading", "sentence", "sentence", "sentence", "sentence", "check", "table", "foot",
  ]);
  assert.deepEqual(revealParts(x02, data.sources, false).slice(-3), ["check", "warnings", "foot"]); // validation rewrote it
  assert.deepEqual(revealParts({ ...n01, degraded: true }, data.sources, false).slice(-2), ["note", "foot"]);
  assert.deepEqual(revealParts(n01, undefined, true), ["read", "source", "heading", "sentence", "check", "table", "foot"]); // no lookup, no filing named
  assert.deepEqual(revealParts(o02, undefined, false), ["read", "heading", "sentence", "foot"]); // a refusal: nothing cited or checked
  const own = { ...o02, refused: false, reading: null, own_data: true };
  assert.deepEqual(revealParts(own, undefined, false), ["heading", "sentence", "note", "foot"]); // its own data: a note, no source
  assert.deepEqual(revealParts({ ...x04, reading: null }, data.sources, false).slice(0, 2), ["source", "filings"]);
  assert.deepEqual(revealParts(x04, undefined, false).slice(0, 2), ["read", "heading"], "the sources wait for the lookup");
  assert.equal(landed(x04, undefined, false), false);
});

test("the answer comes sentence by sentence, the text kept whole, with no break inside U.S. or a figure", () => {
  const data = snapshot();
  for (const { answer } of data.answers) assert.equal(sentences(answer.answer).join(""), answer.answer);
  assert.deepEqual(["n01", "x04", "c02", "c12"].map((id) => sentences(saved(data, id).answer).length), [1, 2, 3, 4]);
  assert.deepEqual(sentences("U.S. sales rose 2.5% to $1.2 billion [1]. Costs fell [2]."), ["U.S. sales rose 2.5% to $1.2 billion [1]. ", "Costs fell [2]."]);
});

test("the reveal: the pull, then about 0.3 s between parts, the last in place within 3 s of the data however long the answer", () => {
  assert.equal(STEP_MS, 300);
  assert.deepEqual(revealTimes(3, true), [PULL_MS, PULL_MS + STEP_MS, PULL_MS + 2 * STEP_MS]);
  assert.deepEqual(revealTimes(2, false), [0, STEP_MS]);
  for (const pull of [true, false]) {
    for (let n = 1; n <= 80; n++) {
      const times = revealTimes(n, pull);
      assert.equal(times.length, n);
      assert.ok(times.at(-1)! + ENTER_MS < 3000, `${n} parts, pull ${pull}: the last in place at ${times.at(-1)! + ENTER_MS} ms`);
      times.slice(1).forEach((at, i) => assert.ok(at > times[i] && at - times[i] <= STEP_MS, `${n} parts: step ${i + 1}`));
    }
  }
  const apple = revealTimes(8, true); // n01's eight parts after the pull keep near 0.3 s
  assert.ok(apple[1] - apple[0] >= 250, `${apple[1] - apple[0]} ms`);
});

test("the stage comes to rest by itself within 5 s (WCAG 2.2.2): the sources let go a second after the card settles, then the drift slows to a stop", () => {
  // Rest starts at the page load, or as the last part starts; the card is in place ENTER_MS after that.
  assert.equal(RELEASE_MS, 1_000);
  assert.ok(CALM_MS <= 5_000, `still ${CALM_MS} ms after the page load`);
  assert.equal(calmPace(0), 1);
  assert.equal(calmPace(ENTER_MS + RELEASE_MS + 1_200), 1, "the sources let go and drift home at full pace");
  assert.equal(calmPace(CALM_MS), 0);
  assert.equal(calmPace(60_000), 0);
  for (let ms = 0; ms < CALM_MS; ms += 50) assert.ok(calmPace(ms + 50) <= calmPace(ms), `slows, never speeds up, at ${ms} ms`);
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

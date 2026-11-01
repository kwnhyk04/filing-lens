// The hero's story under `node --test`: a saved answer from the demo snapshot, as the landing page tells it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { Snapshot } from "./demo.ts";
import { heroStory, STORY } from "./story.ts";

const snapshot = (): Snapshot =>
  JSON.parse(readFileSync(new URL("../demo/snapshot.json", import.meta.url), "utf8")) as Snapshot;

test("the hero tells x12: its question, its reading, its two passages and its check", () => {
  const data = snapshot();
  const saved = data.answers.find((item) => item.id === STORY);
  assert.ok(saved);
  const story = heroStory(data);
  assert.equal(story.question, saved.question);
  assert.equal(story.answer, saved.answer);
  assert.deepEqual(story.reading, ["Text question", "ELI LILLY & Co"]);
  assert.deepEqual(
    story.passages.map(({ n, label, item, quote }) => ({ n, label, item, quote })),
    [
      { n: 1, label: "LLY 10-K FY2025, Item 7", item: "7", quote: saved.answer.citations[0].quote },
      { n: 2, label: "LLY 10-K FY2025, Item 1A", item: "1A", quote: saved.answer.citations[1].quote },
    ],
  );
  assert.deepEqual(story.checks, [{ n: 2, text: "56 percent", value: "56" }]);
  assert.equal(story.filing, "LLY 10-K FY2025");
});

test("every quote the hero shows is in its passage word for word, as the page says", () => {
  const story = heroStory(snapshot());
  assert.deepEqual(
    story.sources.chunks.map((chunk) => chunk.id),
    story.answer.citations.map((citation) => citation.chunk_id),
  );
  story.passages.forEach((passage, i) => assert.ok(story.sources.chunks[i].text.includes(passage.quote)));
  for (const check of story.checks) assert.ok(story.passages[check.n - 1].quote.includes(check.text));
});

test("the filings that float around the story are the snapshot's others, as form and year", () => {
  const story = heroStory(snapshot());
  assert.equal(story.others.length, snapshot().companies.length - 1);
  assert.ok(!story.others.some((filing) => filing.startsWith("LLY ")));
  assert.ok(story.others.every((filing) => /^[A-Z.]+ 10-K FY20\d\d$/.test(filing)));
});

test("a refused answer, or one that cites no passage, cannot be the hero's story", () => {
  const refused = snapshot();
  const x12 = refused.answers.find((item) => item.id === STORY);
  assert.ok(x12);
  x12.answer = { ...x12.answer, refused: true };
  assert.throws(() => heroStory(refused), /x12 is refused/);

  const facts = snapshot();
  const n01 = facts.answers.find((item) => item.id === "n01");
  assert.ok(n01);
  assert.throws(() => heroStory(facts, "n01"), /n01 cites a source that is not a passage/);
  assert.throws(() => heroStory(facts, "zz9"), /no answer zz9/);
});

// The hero's story under `node --test`: a saved answer from the demo snapshot, as the landing page tells it.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { Snapshot } from "./demo.ts";
import { checkLine, heroStories, heroStory, LOOP, QUOTE, STORY, storyBeats } from "./story.ts";

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

test("a refused answer, or one that cites neither a passage nor a fact, cannot be the hero's story", () => {
  const refused = snapshot();
  const x12 = refused.answers.find((item) => item.id === STORY);
  assert.ok(x12);
  x12.answer = { ...x12.answer, refused: true };
  assert.throws(() => heroStory(refused), /x12 is refused/);

  const calculated = snapshot();
  const n01 = calculated.answers.find((item) => item.id === "n01");
  assert.ok(n01);
  const [citation] = n01.answer.citations;
  n01.answer = { ...n01.answer, citations: [{ ...citation, fact_id: null, calculation: { inputs: [1, 2] } }] };
  assert.throws(() => heroStory(calculated, "n01"), /n01 cites a source that is not a passage or a fact/);
  assert.throws(() => heroStory(calculated, "zz9"), /no answer zz9/);
});

test("the moving hero loops through x12, then short answers from other companies, none the overview's", () => {
  const data = snapshot();
  const stories = heroStories(data);
  assert.deepEqual(LOOP, ["x12", "n01", "c02"]);
  assert.ok(!LOOP.includes(QUOTE)); // the overview just below the hero shows that answer already
  assert.deepEqual(
    stories.map((story) => story.question),
    LOOP.map((id) => data.answers.find((item) => item.id === id)?.question),
  );
  assert.equal(stories[0].question, heroStory(data).question); // the still's story comes first
  const tickers = stories.map((story) => story.filings.map((filing) => filing.split(" ")[0]));
  assert.deepEqual(tickers, [["LLY"], ["AAPL"], ["GOOGL", "META"]]); // no company twice
  for (const story of stories) {
    assert.equal(story.answer.refused, false);
    assert.deepEqual(story.answer.warnings, []);
    assert.ok(story.answer.answer.length <= 300, story.question);
  }
});

test("an answer that cites facts shows each fact's value, its filing and its check", () => {
  const data = snapshot();
  const n01 = heroStory(data, "n01");
  assert.deepEqual(n01.passages, [
    {
      n: 1,
      kind: "fact",
      label: "AAPL fact, Revenue from Contract with Customer, Excluding Assessed Tax, period ending 2025-09-27",
      filing: "AAPL 10-K FY2025",
      quote: "416,161,000,000 USD",
    },
  ]);
  assert.deepEqual(n01.checks, [{ n: 1, text: "416,161,000,000", value: "416,161,000,000" }]);
  assert.deepEqual(n01.sources.facts.map((fact) => fact.id), ["37437"]);

  const c02 = heroStory(data, "c02");
  assert.deepEqual(c02.filings, ["GOOGL 10-K FY2025", "META 10-K FY2025"]);
  assert.equal(c02.filing, "GOOGL 10-K FY2025 and META 10-K FY2025");
  assert.equal(c02.others.length, data.companies.length - 2);
  assert.ok(!c02.others.some((filing) => /^(GOOGL|META) /.test(filing)));
});

test("every check of every story in the loop matches its cited quote or fact", () => {
  for (const story of heroStories(snapshot())) {
    for (const check of story.checks) {
      const source = story.passages[check.n - 1];
      if (source.kind === "passage") assert.ok(source.quote.includes(check.text), check.text);
      else {
        const fact = story.sources.facts[story.passages.filter((p) => p.kind === "fact").indexOf(source)];
        assert.equal(Number(check.value.replaceAll(",", "")), fact.value, check.text);
      }
    }
  }
});

test("each story's caption and check line say what it cites: passages, or facts and their amounts", () => {
  const [x12, n01, c02] = heroStories(snapshot());
  const x04 = heroStory(snapshot(), "x04"); // out of the loop, but still the passage answer with no amount to check
  assert.deepEqual(
    storyBeats(x12).map((beat) => beat.cue),
    [
      "A question about a filing.",
      "FilingLens reads it: the company, the years, the kind of question.",
      "Read as Text question · ELI LILLY & Co.",
      "Two passages from LLY 10-K FY2025 hold the answer.",
      "Each sentence cites its passage, and a check matches every quote and amount.",
      "An answer you can check.",
    ],
  );
  assert.equal(storyBeats(x04)[3].cue, "One passage from AMZN 10-K FY2025 holds the answer.");
  assert.equal(storyBeats(n01)[3].cue, "One fact from AAPL 10-K FY2025 holds the answer.");
  assert.equal(storyBeats(n01)[4].cue, "Each sentence cites its fact, and a check matches every amount.");
  assert.equal(storyBeats(c02)[3].cue, "Two facts from GOOGL 10-K FY2025 and META 10-K FY2025 hold the answer.");
  assert.equal(checkLine(x12), "Checked: 56 percent matches source 2, and every quote matches its passage word for word.");
  assert.equal(checkLine(x04), "Checked: every quote matches its passage word for word.");
  assert.equal(checkLine(n01), "Checked: 416,161,000,000 matches source 1.");
  assert.equal(
    checkLine(c02),
    "Checked: $402,836,000,000 matches source 1 and $200,966,000,000 matches source 2.",
  );
});

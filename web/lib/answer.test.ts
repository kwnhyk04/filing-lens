// The answer helpers under `node --test`: SSE framing, quote highlighting, citation markers.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answerWithSources,
  createSseParser,
  formLabel,
  locateQuote,
  periodEnded,
  splitFigures,
  splitMarkers,
  timingLine,
  type Answer,
} from "./answer.ts";

function parse(chunks: string[]): string[] {
  const data: string[] = [];
  const push = createSseParser((event) => data.push(event));
  for (const chunk of chunks) push(chunk);
  return data;
}

test("SSE: events split across reads, keep-alive comments skipped", () => {
  const wire = ': ping\n\ndata: {"type":"delta","text":"Hi"}\n\n: ping\n\ndata: {"type":"completed"}\n\n';
  const expected = ['{"type":"delta","text":"Hi"}', '{"type":"completed"}'];
  assert.deepEqual(parse([wire]), expected);
  for (const size of [1, 2, 3, 7]) {
    const chunks = wire.match(new RegExp(`[\\s\\S]{1,${size}}`, "g")) ?? [];
    assert.deepEqual(parse(chunks), expected, `reads of ${size} characters`);
  }
});

test("SSE: CRLF line ends, several data lines, and an unfinished event held back", () => {
  assert.deepEqual(parse(["data: a\r\ndata: b\r\n\r\ndata: c"]), ["a\nb"]);
});

const TEXT = "Revenue rose 5% in the U.S.,  driven by “strong demand” for iPhoneﬁ.";

test("a quote is found through NFKC, curly quotes and runs of whitespace", () => {
  const span = locateQuote(TEXT, 'in the U.S., driven by "strong demand"');
  assert.ok(span);
  assert.equal(TEXT.slice(span.start, span.end), "in the U.S.,  driven by “strong demand”");
  const ligature = locateQuote(TEXT, "for iPhonefi");
  assert.ok(ligature);
  assert.equal(TEXT.slice(ligature.start, ligature.end), "for iPhoneﬁ");
});

test("a changed word, digit or letter case is not found", () => {
  assert.equal(locateQuote(TEXT, "Revenue rose 6%"), null);
  assert.equal(locateQuote(TEXT, "driven by strong supply"), null);
  assert.equal(locateQuote(TEXT, "revenue rose"), null);
  assert.equal(locateQuote(TEXT, "   "), null);
});

test("GraphQL's form enum reads as the SEC form", () => {
  assert.deepEqual(["FORM_10K", "FORM_10Q"].map(formLabel), ["10-K", "10-Q"]);
});

test("a filing's period end: its fiscal year for a 10-K, its quarter for a 10-Q, as a long date in UTC", () => {
  assert.equal(periodEnded("FY", "2025-09-27"), "Fiscal year ended September 27, 2025");
  assert.equal(periodEnded("FY", "2025-12-31"), "Fiscal year ended December 31, 2025");
  assert.equal(periodEnded("Q2", "2025-03-29"), "Quarter ended March 29, 2025");
});

test("markers become citation numbers; one past the citations stays text", () => {
  assert.deepEqual(splitMarkers("Up [1]. Down [2][3].", 2), ["Up ", 1, ". Down ", 2, "", "[3]", "."]);
});

test("figures: amounts with a currency, a unit or a scale split out; years, dates and item numbers stay text", () => {
  const text = "In fiscal 2025, revenue was 416,161,000,000 USD, $402,836,000,000, $3,855 million and 56 percent, up 12.5%.";
  assert.deepEqual(splitFigures(text), [
    "In fiscal 2025, revenue was ",
    "416,161,000,000 USD",
    ", ",
    "$402,836,000,000",
    ", ",
    "$3,855 million",
    " and ",
    "56 percent",
    ", up ",
    "12.5%",
    ".",
  ]);
  const none = "A 10-K for fiscal year 2026, Item 7, filed on September 15, 2025.";
  assert.deepEqual(splitFigures(none), [none]);
});

test("timings: first words, completion and the source count, in seconds to one decimal", () => {
  assert.equal(timingLine(940, 2610, 2), "First words in 0.9 s · complete in 2.6 s · 2 sources");
  assert.equal(timingLine(30, 310, 1), "First words in 0.0 s · complete in 0.3 s · 1 source");
});

test("timings: no draft text means no first words, and a refusal counts no sources", () => {
  assert.equal(timingLine(undefined, 870, 0), "Complete in 0.9 s");
});

const CITED: Answer = {
  answer: "Revenue was $1.2 billion [1], up 5% [2].",
  citations: [
    { chunk_id: "c-1", fact_id: null, quote: "$1.2 billion", filing_url: "https://www.sec.gov/a" },
    { chunk_id: null, fact_id: "f-1", quote: "5%", filing_url: "https://www.sec.gov/b" },
  ],
  degraded: false,
  refused: false,
  usage: { input_tokens: 1, output_tokens: 1, cost_usd: 0 },
  warnings: [],
};

test("copied text: the answer with its markers, then each source's name, quote and link", () => {
  assert.equal(
    answerWithSources(CITED, ["AAPL 10-K FY2025, Item 7", "AAPL fact, Revenues, period ending 2025-09-27"]),
    [
      "Revenue was $1.2 billion [1], up 5% [2].",
      "",
      "Sources",
      '[1] AAPL 10-K FY2025, Item 7: "$1.2 billion" https://www.sec.gov/a',
      '[2] AAPL fact, Revenues, period ending 2025-09-27: "5%" https://www.sec.gov/b',
    ].join("\n"),
  );
});

test("copied text: a source whose card has not loaded keeps its quote and link", () => {
  assert.equal(answerWithSources(CITED, []).split("\n").at(-1), '[2] "5%" https://www.sec.gov/b');
});

// The answer helpers under `node --test`: SSE framing, quote highlighting, citation markers.
import assert from "node:assert/strict";
import { test } from "node:test";

import { createSseParser, formLabel, locateQuote, splitFigures, splitMarkers } from "./answer.ts";

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

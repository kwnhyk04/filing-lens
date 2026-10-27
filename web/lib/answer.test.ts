// The answer helpers under `node --test`: SSE framing, quote highlighting, citation markers.
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  answerWithSources,
  checksTitle,
  createSseParser,
  figureRows,
  formLabel,
  locateQuote,
  periodEnded,
  readingChips,
  sourceLabel,
  splitFigures,
  splitMarkers,
  timingLine,
  type Answer,
  type Reading,
} from "./answer.ts";
import type { Sources } from "./demo.ts";

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
    { chunk_id: "c-1", fact_id: null, calculation: null, quote: "$1.2 billion", filing_url: "https://www.sec.gov/a" },
    { chunk_id: null, fact_id: "f-1", calculation: null, quote: "5%", filing_url: "https://www.sec.gov/b" },
  ],
  degraded: false,
  refused: false,
  usage: { input_tokens: 1, output_tokens: 1, cost_usd: 0 },
  warnings: [],
  reading: null,
  checks: [],
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

const read = (reading: Partial<Reading>): Reading => ({
  route: "numeric",
  companies: [],
  other_companies: [],
  fiscal_years: [],
  fiscal_period: null,
  metric: null,
  ...reading,
});

test("Read as: the kind, each company, the years in order, a quarter and the figure in words", () => {
  const apple = [{ ticker: "AAPL", name: "Apple Inc." }];
  assert.deepEqual(readingChips(read({ companies: apple, fiscal_years: [2025], fiscal_period: "FY", metric: "revenue" })), [
    "Number question",
    "Apple Inc.",
    "Fiscal 2025",
    "Revenue",
  ]);
  const tesla = [{ ticker: "TSLA", name: "Tesla, Inc." }];
  assert.deepEqual(readingChips(read({ route: "comparison", companies: tesla, fiscal_years: [2025, 2024], metric: "net_income" })), [
    "Comparison",
    "Tesla, Inc.",
    "Fiscal 2024 and 2025",
    "Net income",
  ]);
  assert.deepEqual(readingChips(read({ route: "out_of_scope" })), ["Out of scope"]);
  const quarter = read({ route: "textual", other_companies: ["Acme"], fiscal_years: [2023, 2025, 2024], fiscal_period: "Q2", metric: "eps_diluted" });
  assert.deepEqual(readingChips(quarter), ["Text question", "Acme", "Fiscal 2023, 2024 and 2025", "Q2", "Diluted EPS"]);
  assert.deepEqual(readingChips(read({ metric: "free_cash_flow" })), ["Number question", "Free cash flow"]); // not in the map
});

const CHECKED = {
  answer: "Net income was $3,794 million [1], and $3,855 million in total [2].",
  citations: [
    { chunk_id: null, fact_id: "330860", quote: "3,794,000,000 USD", filing_url: "https://www.sec.gov/a" },
    { chunk_id: "c-3", fact_id: null, quote: "Net income | $ | 3,855", filing_url: "https://www.sec.gov/b" },
  ],
  checks: [
    { text: "$3,794 million", citation: 1, source_value: "3,794,000,000" },
    { text: "$3,855 million", citation: 2, source_value: "3,855" },
  ],
} as unknown as Answer;
const FOUND = {
  facts: [{ id: "330860", label: "Net Income (Loss) Attributable to Parent", value: 3794000000, unit: "USD", fiscalYear: 2025, fiscalPeriod: "FY", periodEnd: "2025-12-31", company: { ticker: "TSLA" } }],
  chunks: [{ id: "c-3", section: { item: "8" }, filing: { formType: "FORM_10K", fiscalYear: 2025, company: { ticker: "TSLA" } } }],
} as unknown as Sources;

test("number checks: a fact's label and value, a passage's name and the number as quoted", () => {
  assert.deepEqual(figureRows(CHECKED, FOUND), [
    { figure: "Net Income (Loss) Attributable to Parent, period ending 2025-12-31", written: "$3,794 million", reported: "3,794,000,000 USD" },
    { figure: "TSLA 10-K FY2025, Item 8", written: "$3,855 million", reported: "3,855, as quoted" },
  ]);
  assert.deepEqual(figureRows(CHECKED, undefined), [
    { figure: "Source 1", written: "$3,794 million", reported: "3,794,000,000" },
    { figure: "Source 2", written: "$3,855 million", reported: "3,855" },
  ]); // before the sources load
  assert.equal(checksTitle(CHECKED), "Numbers checked against their sources");
  assert.equal(checksTitle({ ...CHECKED, checks: CHECKED.checks.slice(0, 1) }), "Numbers checked against XBRL data");
});

// c02 with a calculation (K1): FilingLens's arithmetic on its two cited facts.
const CALCULATED = {
  answer: "Alphabet's $402.8 billion was $201.9 billion higher than Meta's $201.0 billion [1][2][3].",
  citations: [
    { chunk_id: null, fact_id: "380121", calculation: null, quote: "402,836,000,000 USD", filing_url: "https://www.sec.gov/a" },
    { chunk_id: null, fact_id: "206185", calculation: null, quote: "200,966,000,000 USD", filing_url: "https://www.sec.gov/b" },
    {
      chunk_id: null,
      fact_id: null,
      calculation: { inputs: [1, 2] },
      quote: "Alphabet Inc. (GOOGL) is higher by 201,870,000,000 USD, 100.45% more than Meta Platforms, Inc. (META).",
      filing_url: "https://www.sec.gov/b",
    },
  ],
  checks: [{ text: "$201.9 billion", citation: 3, source_value: "201,870,000,000" }],
} as unknown as Answer;

test("a calculation reads as FilingLens's arithmetic on the sources it names, with no lookup", () => {
  assert.equal(sourceLabel(CALCULATED.citations[2]), "Calculated by FilingLens from sources 1 and 2");
  assert.deepEqual(figureRows(CALCULATED, undefined), [
    { figure: "Calculated by FilingLens from sources 1 and 2", written: "$201.9 billion", reported: "201,870,000,000, calculated" },
  ]);
  assert.equal(checksTitle(CALCULATED), "Numbers checked against XBRL data"); // arithmetic on XBRL facts
});

test("the timing line says every number was checked when the answer has checks", () => {
  assert.equal(timingLine(900, 2600, 2, true), "First words in 0.9 s · complete in 2.6 s · 2 sources · every number checked");
});

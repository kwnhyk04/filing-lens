// Answer display helpers, safe in the browser: SSE framing, quote highlighting, citation markers, the
// timing line, the copied text, the router's reading and the number checks.
import type { components } from "../../clients/ts/index.ts";
import type { Sources } from "./demo.ts";

type Schemas = components["schemas"];
export type Answer = Schemas["Answer"];
export type AnswerEvent = Schemas["AnswerDelta"] | Schemas["AnswerCompleted"] | Schemas["AnswerFailed"];
export type Reading = Schemas["Reading"];
type Citation = Answer["citations"][number];

/** The chunk or the fact a citation names, once the sources have loaded. */
export function findSource(citation: Citation, sources?: Sources) {
  return {
    chunk: citation.chunk_id ? sources?.chunks.find((chunk) => chunk.id === citation.chunk_id) : undefined,
    fact: citation.fact_id ? sources?.facts.find((fact) => fact.id === citation.fact_id) : undefined,
  };
}

/** "NVDA 10-K FY2026, Item 1A" once the sources load; a calculation names its sources at once. */
export function sourceLabel(citation: Citation, sources?: Sources): string | undefined {
  if (citation.calculation) return `Calculated by FilingLens from sources ${listed(citation.calculation.inputs.map(String))}`;
  const { chunk, fact } = findSource(citation, sources);
  if (chunk) {
    const { company, formType, fiscalYear } = chunk.filing;
    return `${company.ticker} ${formLabel(formType)} FY${fiscalYear}, Item ${chunk.section.item}`;
  }
  // A fact's fiscal year is its reporting filing's, so the period end names the value's own date.
  if (fact) return `${fact.company.ticker} fact, ${fact.label}, period ending ${fact.periodEnd}`;
}

const KINDS: Record<Reading["route"], string> = {
  numeric: "Number question",
  comparison: "Comparison",
  textual: "Text question",
  out_of_scope: "Out of scope",
};
// Figures whose key in words reads wrong; any other key reads as its words.
const FIGURES: Record<string, string> = {
  eps_diluted: "Diluted EPS",
  eps_basic: "Basic EPS",
  stockholders_equity: "Stockholders' equity",
  long_term_debt: "Long-term debt",
};

const listed = (items: string[]) => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`);

/** How the router read a question: its kind, the companies, the years, a quarter and the figure. */
export function readingChips(reading: Reading): string[] {
  const chips = [KINDS[reading.route], ...reading.companies.map((company) => company.name), ...reading.other_companies];
  const years = [...reading.fiscal_years].sort((a, b) => a - b).map(String);
  if (years.length) chips.push(`Fiscal ${listed(years)}`);
  if (reading.fiscal_period && reading.fiscal_period !== "FY") chips.push(reading.fiscal_period);
  if (reading.metric) {
    const words = reading.metric.replaceAll("_", " ");
    chips.push(FIGURES[reading.metric] ?? words[0].toUpperCase() + words.slice(1));
  }
  return chips;
}

const number = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 10 });

export interface FigureRow {
  figure: string;
  written: string;
  reported: string;
}

/** Each checked amount: what it is, as the answer writes it, and as its source reports it. */
export function figureRows(answer: Answer, sources?: Sources): FigureRow[] {
  return answer.checks.map((check) => {
    const citation = answer.citations[check.citation - 1];
    if (citation.calculation) {
      return { figure: sourceLabel(citation) ?? "", written: check.text, reported: `${check.source_value}, calculated` };
    }
    const { chunk, fact } = findSource(citation, sources);
    if (fact) {
      const figure = `${fact.label}, period ending ${fact.periodEnd}`;
      return { figure, written: check.text, reported: `${number(fact.value)} ${fact.unit}` };
    }
    if (chunk) {
      return { figure: sourceLabel(citation, sources) ?? "", written: check.text, reported: `${check.source_value}, as quoted` };
    }
    return { figure: `Source ${check.citation}`, written: check.text, reported: check.source_value };
  });
}

/** "against XBRL data" when every checked amount cites a fact or a calculation on facts, else "against their sources". */
export function checksTitle(answer: Answer): string {
  const facts = answer.checks.every((check) => {
    const citation = answer.citations[check.citation - 1];
    return citation?.fact_id || citation?.calculation;
  });
  return `Numbers checked against ${facts ? "XBRL data" : "their sources"}`;
}

/** Feeds text as it arrives; calls `onData` with each event's data, skipping `: ping` comments. */
export function createSseParser(onData: (data: string) => void): (chunk: string) => void {
  let buffer = "";
  return (chunk) => {
    buffer += chunk.replace(/\r/g, ""); // the API ends lines with \n; CRLF is folded the same way
    for (let end = buffer.indexOf("\n\n"); end !== -1; end = buffer.indexOf("\n\n")) {
      const lines = buffer.slice(0, end).split("\n");
      buffer = buffer.slice(end + 2);
      const data = lines.filter((line) => line.startsWith("data:"));
      if (data.length) onData(data.map((line) => line.slice(5).replace(/^ /, "")).join("\n"));
    }
  };
}

// The API's citation check (filinglens_llm.validate): NFKC, straight quotes, single spaces.
const STRAIGHT: Record<string, string> = {
  "‘": "'", "’": "'", "‚": "'", "‛": "'",
  "“": '"', "”": '"', "„": '"', "‟": '"',
};

/** `text` normalized character by character, with each output unit's index in `text`. */
function normalized(text: string): { chars: string; at: number[] } {
  let chars = "";
  const at: number[] = [];
  let index = 0;
  for (const char of text) {
    for (const unit of char.normalize("NFKC")) {
      const out = /\s/.test(unit) ? " " : (STRAIGHT[unit] ?? unit);
      if (out === " " && (chars === "" || chars.endsWith(" "))) continue;
      chars += out;
      for (let i = 0; i < out.length; i++) at.push(index);
    }
    index += char.length;
  }
  return { chars, at };
}

/** Where `quote` sits in `text`, matched as the API checks it; null when it is not there. */
export function locateQuote(text: string, quote: string): { start: number; end: number } | null {
  const wanted = normalized(quote).chars.trim();
  const { chars, at } = normalized(text);
  const found = wanted ? chars.indexOf(wanted) : -1;
  if (found === -1) return null;
  const last = at[found + wanted.length - 1];
  return { start: at[found], end: last + String.fromCodePoint(text.codePointAt(last) ?? 0).length };
}

/** GraphQL's form enum as the SEC writes it: FORM_10K reads 10-K. */
export const formLabel = (form: string) => form.replace(/^FORM_(\d+)([A-Z])$/, "$1-$2");

// In UTC, so a date reads the same on the server and in any browser's time zone.
const LONG_DATE = new Intl.DateTimeFormat("en-US", { dateStyle: "long", timeZone: "UTC" });

/** "Fiscal year ended September 27, 2025" for a 10-K, "Quarter ended March 29, 2025" for a 10-Q. */
export function periodEnded(fiscalPeriod: string, periodEnd: string): string {
  const period = fiscalPeriod === "FY" ? "Fiscal year" : "Quarter";
  return `${period} ended ${LONG_DATE.format(new Date(`${periodEnd}T00:00:00Z`))}`;
}

// A number with a $ before it, or a %, "percent", a scale or USD after it; a bare year never matches.
const FIGURE =
  /(\$\s?\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s(?:thousand|million|billion|trillion)\b)?|\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s?%|\s(?:percent|thousand|million|billion|trillion|USD)\b))/;

/** Splits text around its figures: even indexes are text, odd indexes are figures. */
export const splitFigures = (text: string): string[] => text.split(FIGURE);

const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;

/** "First words in 0.9 s · complete in 2.6 s · 2 sources · every number checked", as the browser timed the stream. */
export function timingLine(firstWordsMs: number | undefined, completeMs: number, sources: number, checked = false): string {
  const parts = [`complete in ${seconds(completeMs)}`];
  if (firstWordsMs !== undefined) parts.unshift(`First words in ${seconds(firstWordsMs)}`);
  if (sources) parts.push(`${sources} source${sources === 1 ? "" : "s"}`);
  if (checked) parts.push("every number checked");
  const line = parts.join(" · ");
  return line[0].toUpperCase() + line.slice(1);
}

/** The answer as copied: its text with the markers, then each source's name (once its card loaded), quote and link. */
export function answerWithSources(answer: Answer, labels: (string | undefined)[]): string {
  const lines = answer.citations.map((citation, i) => {
    const label = labels[i] ? `${labels[i]}: ` : "";
    return `[${i + 1}] ${label}"${citation.quote}" ${citation.filing_url}`;
  });
  return [answer.answer, "", "Sources", ...lines].join("\n");
}

/** Splits an answer at its `[n]` markers; n becomes a number when a citation n exists. */
export function splitMarkers(answer: string, citations: number): (string | number)[] {
  return answer.split(/\[(\d+)\]/).map((part, i) => {
    if (i % 2 === 0) return part;
    const n = Number(part);
    return n >= 1 && n <= citations ? n : `[${part}]`;
  });
}

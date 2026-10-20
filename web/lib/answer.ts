// Answer display helpers, safe in the browser: SSE framing, quote highlighting, citation markers, the
// timing line and the copied text.
import type { components } from "../../clients/ts/index.ts";

type Schemas = components["schemas"];
export type Answer = Schemas["Answer"];
export type AnswerEvent = Schemas["AnswerDelta"] | Schemas["AnswerCompleted"] | Schemas["AnswerFailed"];

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

// A number with a $ before it, or a %, "percent", a scale or USD after it; a bare year never matches.
const FIGURE =
  /(\$\s?\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s(?:thousand|million|billion|trillion)\b)?|\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s?%|\s(?:percent|thousand|million|billion|trillion|USD)\b))/;

/** Splits text around its figures: even indexes are text, odd indexes are figures. */
export const splitFigures = (text: string): string[] => text.split(FIGURE);

const seconds = (ms: number) => `${(ms / 1000).toFixed(1)} s`;

/** "First words in 0.9 s · complete in 2.6 s · 2 sources", as the browser timed the stream. */
export function timingLine(firstWordsMs: number | undefined, completeMs: number, sources: number): string {
  const parts = [`complete in ${seconds(completeMs)}`];
  if (firstWordsMs !== undefined) parts.unshift(`First words in ${seconds(firstWordsMs)}`);
  if (sources) parts.push(`${sources} source${sources === 1 ? "" : "s"}`);
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

// Ask's stage, the live version of the landing hero's story: its phase from what the answer stream and the sources
// lookup have reported, the card's parts in the hero's order with the reveal's schedule, and what floats round it.
// While FilingLens reads, only the covered filings float; once the sources load, each cited source takes its own
// filing's place, so nothing is claimed before it is known.
import { checkLine, citedFilings, filingName, findSource, formLabel, sourceFiling, type Answer } from "./answer.ts";
import type { Company, Sources } from "./demo.ts";

export type Kind = "passage" | "fact" | "filing";
/** What floats: a covered filing, or a cited passage or fact; `filing` names the filing it belongs to. */
export type Thing = { kind: Kind; title: string; sub: string; icon: string; filing: string };
/** What the answer stream and the sources lookup have reported. */
export type Phase = "empty" | "reading" | "done" | "failed";
/** Where the stage is: the data's phase, or the sequence that shows it (the pull, the reveal) and the leave. */
export type View = Phase | "pulling" | "revealing" | "leaving";
/** The card's parts after the question, in the hero's order; a source and a sentence come once each. */
export type Part = "read" | "source" | "filings" | "heading" | "sentence" | "check" | "table" | "warnings" | "note" | "foot";

/** What Ask's moving stage plays from: where the stage is, the covered filings and, from the pull on, the cited ones. */
export interface StageProps {
  phase: View;
  covered: Thing[];
  cited: Thing[];
}

/** The places round the stage, as the hero's; one stays free, as there. */
export const SLOTS = 12;

/** The sequence in ms: the pull, the most between two parts, a part's way in (the card growing to take it), the
    reveal from the data to the last part in place, the leave, the flight. */
export const PULL_MS = 700;
export const STEP_MS = 300;
export const ENTER_MS = 350;
export const REVEAL_MS = 2_950;
export const LEAVE_MS = 450;
export const FLY_MS = 450;
/** Once the card is in place, the membrane holds its sources this long, then lets them go. */
export const RELEASE_MS = 1_000;
/** The stage stops moving this long after it comes to rest (the page load, an answer done, an error): with no Pause
    button, its motion must end within 5 s (WCAG 2.2.2). */
export const CALM_MS = 4_500;

/** How fast the floating things drift `ms` after the stage came to rest: full pace, then over the last second it slows
    to a stop. */
export function calmPace(ms: number): number {
  const x = Math.min(1, Math.max(0, (CALM_MS - ms) / 1_000));
  return x * x * (3 - 2 * x);
}

const sentenceBreaks = new Intl.Segmenter("en", { granularity: "sentence" });
/** The answer's sentences, each with the space after it, so they join back into the text. */
export const sentences = (text: string) => Array.from(sentenceBreaks.segment(text), ({ segment }) => segment);

interface State {
  asked: string | null;
  answer: Answer | null;
  sources?: Sources;
  sourcesFailed: boolean;
  problem: boolean;
}

const needsLookup = (answer: Answer) => answer.citations.some((citation) => citation.chunk_id || citation.fact_id);

/** Empty, reading (sent, until the checked answer and, when it cites a passage or fact, its sources are in), done,
    or failed. */
export function stagePhase({ asked, answer, sources, sourcesFailed, problem }: State): Phase {
  if (asked === null) return "empty";
  if (problem) return "failed";
  if (!answer) return "reading";
  return sources || sourcesFailed || !needsLookup(answer) ? "done" : "reading";
}

/** Whether the answer's passages can show: it cites something, and its sources are in, failed, or need no lookup. */
export const landed = (answer: Answer, sources: Sources | undefined, failed: boolean) =>
  answer.citations.length > 0 && (sources !== undefined || failed || !needsLookup(answer));

/** The parts this answer has, in the hero's order: Read as, each source and the filings they come from once the
    lookup is in, the heading, each sentence, the check line, the number checks, the notes, the foot. */
export function revealParts(answer: Answer, sources: Sources | undefined, failed: boolean): Part[] {
  const cited = landed(answer, sources, failed);
  const each = (count: number, part: Part): Part[] => Array(count).fill(part);
  return [
    ...each(Number(Boolean(answer.reading)), "read"),
    ...each(cited ? answer.citations.length : 0, "source"),
    ...each(Number(cited && citedFilings(answer, sources).length > 0), "filings"),
    "heading",
    ...each(sentences(answer.answer).length, "sentence"),
    ...each(Number(checkLine(answer) !== undefined), "check"),
    ...each(Number(answer.checks.length > 0), "table"),
    ...each(Number(answer.warnings.length > 0), "warnings"),
    ...each(Number(answer.degraded), "note"),
    "foot",
  ];
}

/** When each of `n` parts starts, in ms from the data: after the pull when there is one, then STEP_MS apart, or
    closer, so the last is in place within REVEAL_MS however long the answer. */
export function revealTimes(n: number, pull: boolean): number[] {
  const start = pull ? PULL_MS : 0;
  const step = n > 1 ? Math.min(STEP_MS, (REVEAL_MS - ENTER_MS - start) / (n - 1)) : 0;
  return Array.from({ length: n }, (_, i) => Math.round(start + i * step));
}

/** The stage's view: the leave over everything; else the data's phase, which once done is the pull, the reveal or
    done, by how many of the card's `parts` show (`step`). */
export function stageView(phase: Phase, { step, parts, pull, leaving }: { step: number; parts: number; pull: boolean; leaving: boolean }): View {
  if (leaving) return "leaving";
  if (phase !== "done") return phase;
  if (step >= parts) return "done";
  return step === 0 && pull ? "pulling" : "revealing";
}

/** Each covered filing as it floats, "AMZN 10-K" over "FY2025", as many as there are places but one. */
export function coveredThings(companies: Company[]): Thing[] {
  return companies
    .flatMap(({ ticker, filings }) =>
      filings.edges.map(({ node }): Thing => {
        const form = formLabel(node.formType);
        const sub = `FY${node.fiscalYear}${node.fiscalPeriod === "FY" ? "" : ` ${node.fiscalPeriod}`}`;
        return { kind: "filing", title: `${ticker} ${form}`, sub, icon: "file", filing: filingName(ticker, form, node.fiscalYear, node.fiscalPeriod) };
      }),
    )
    .slice(0, SLOTS - 1);
}

/** Each cited passage or fact once the sources load, a passage by its item and a fact by its value. */
export function citedThings(answer: Answer, sources?: Sources): Thing[] {
  return answer.citations.flatMap((citation): Thing[] => {
    const filing = sourceFiling(citation, sources);
    if (!filing) return []; // not loaded yet, or FilingLens's own arithmetic
    const { chunk } = findSource(citation, sources);
    return [
      chunk
        ? { kind: "passage", title: `Item ${chunk.section.item}`, sub: filing.name, icon: "file-text", filing: filing.name }
        : { kind: "fact", title: citation.quote, sub: filing.name, icon: "hash", filing: filing.name },
    ];
  });
}

/** The things in their places: the covered filings where they float, and each cited source in its own filing's
    place, else an empty one, else the last uncited filing's. `pulls`: each cited source's place, in turn. */
export function placeThings(covered: Thing[], cited: Thing[]): { env: (Thing | null)[]; pulls: number[] } {
  const env: (Thing | null)[] = Array.from({ length: SLOTS - 1 }, (_, i) => covered[i] ?? null);
  const cites = new Set(cited.map((thing) => thing.filing));
  const pulls: number[] = [];
  for (const thing of cited) {
    const free = (i: number) => !pulls.includes(i);
    let at = env.findIndex((t, i) => free(i) && t?.kind === "filing" && t.filing === thing.filing);
    if (at === -1) at = env.findIndex((t, i) => free(i) && t === null);
    if (at === -1) at = env.findLastIndex((t, i) => free(i) && t?.kind === "filing" && !cites.has(t.filing));
    if (at === -1) continue; // more cited sources than places
    env[at] = thing;
    pulls.push(at);
  }
  return { env, pulls };
}

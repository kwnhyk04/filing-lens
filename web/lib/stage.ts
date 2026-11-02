// Ask's stage, the live version of the landing hero: its phase from what the answer stream and the sources
// lookup have reported, and what floats round it. While FilingLens reads, only the covered filings float; once
// the sources load, each cited source takes its own filing's place, so nothing is claimed before it is known.
import { filingName, findSource, formLabel, sourceFiling, type Answer } from "./answer.ts";
import type { Company, Sources } from "./demo.ts";

export type Kind = "passage" | "fact" | "filing";
/** What floats: a covered filing, or a cited passage or fact; `filing` names the filing it belongs to. */
export type Thing = { kind: Kind; title: string; sub: string; icon: string; filing: string };
export type Phase = "empty" | "reading" | "answered" | "done" | "failed";

/** What Ask's moving stage plays from: the phase, the question's turn, the covered filings and, once the sources
    load, the cited ones. */
export interface StageProps {
  phase: Phase;
  turn: number;
  covered: Thing[];
  cited: Thing[];
}

/** The places round the stage, as the hero's; one stays free, as there. */
export const SLOTS = 12;

interface State {
  asked: string | null;
  answer: Answer | null;
  sources?: Sources;
  sourcesFailed: boolean;
  problem: boolean;
}

/** Empty, reading (sent, nothing checked yet), answered (checked, its sources still loading), done, or failed. */
export function stagePhase({ asked, answer, sources, sourcesFailed, problem }: State): Phase {
  if (asked === null) return "empty";
  if (problem) return "failed";
  if (!answer) return "reading";
  return sources || sourcesFailed || !answer.citations.length ? "done" : "answered";
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

// The demo snapshot from `make demo-export`, imported at build time: rebuild after a new export.
import type { CoverageQuery, SourcesQuery } from "../../clients/ts/index.ts";
import snapshot from "../demo/snapshot.json";
import type { Answer } from "./answer.ts";
import { coverageLine } from "./coverage.ts";

export type Sources = SourcesQuery;
export type Company = CoverageQuery["companies"]["edges"][number]["node"];

export interface DemoAnswer {
  id: string;
  category: string;
  question: string;
  answer: Answer;
}

export interface Snapshot {
  answers: DemoAnswer[];
  commit: string;
  companies: Company[];
  recorded_at: string;
  report: string;
  source: string;
  sources: Sources;
}

export const demo = snapshot as unknown as Snapshot;

const listed = demo.companies.reduce((sum, company) => sum + company.filings.edges.length, 0);
const unlisted = demo.companies.some((company) => company.filings.pageInfo.hasNextPage);
/** "30 companies · 30 filings": what the snapshot covers, with "+" when it left older filings out. */
export const demoCoverageLine = coverageLine(demo.companies.length, listed, unlisted);

/** The companies, from the one after CIK `after` when an old pager's link carries one; null for a cursor the
    snapshot lacks. The page pages them itself (components/coverage-table.tsx). */
export function demoCoverage(after?: string): Company[] | null {
  const start = after === undefined ? 0 : demo.companies.findIndex((c) => String(c.cik) === after) + 1;
  return after !== undefined && start === 0 ? null : demo.companies.slice(start);
}

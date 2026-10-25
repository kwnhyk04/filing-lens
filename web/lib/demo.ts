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
const PAGE = 20;

const listed = demo.companies.reduce((sum, company) => sum + company.filings.edges.length, 0);
const unlisted = demo.companies.some((company) => company.filings.pageInfo.hasNextPage);
/** "30 companies · 30 filings": what the snapshot covers, with "+" when it left older filings out. */
export const demoCoverageLine = coverageLine(demo.companies.length, listed, unlisted);

/** The page of companies after the one with CIK `after`; null for a cursor the snapshot lacks. */
export function demoCoverage(after?: string): { companies: Company[]; next?: string } | null {
  const start = after === undefined ? 0 : demo.companies.findIndex((c) => String(c.cik) === after) + 1;
  if (after !== undefined && start === 0) return null;
  const companies = demo.companies.slice(start, start + PAGE);
  const more = start + PAGE < demo.companies.length;
  return { companies, next: more ? String(companies.at(-1)?.cik) : undefined };
}

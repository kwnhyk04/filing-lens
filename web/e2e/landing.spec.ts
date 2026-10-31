// The public landing page: no session, no API, its links, and every figure from the newest official eval
// report and the demo snapshot, both read here from disk, so a figure typed into the page fails.
import { readdirSync, readFileSync } from "node:fs";

import { evalDate, resultRows, SAMPLE } from "../lib/landing.ts";
import { OFFLINE, snapshot } from "./env.ts";
import { expect, signedOut, signIn, test } from "./fixtures.ts";

const REPORTS = new URL("../../evals/reports/", import.meta.url);
const newest = readdirSync(REPORTS)
  .filter((name) => /^\d{4}-\d{2}-\d{2}\.json$/.test(name))
  .sort()
  .at(-1);
if (!newest) throw new Error("No official report in evals/reports");
const report = JSON.parse(readFileSync(new URL(newest, REPORTS), "utf8"));
const table = readFileSync(new URL(newest.replace(/json$/, "md"), REPORTS), "utf8");
// The same day's Claude-first run, the page's first table; the free-only run above is its second.
const claudeName = newest.replace(/\.json$/, "-claude-first.json");
const claude = JSON.parse(readFileSync(new URL(claudeName, REPORTS), "utf8"));
const claudeTable = readFileSync(new URL(claudeName.replace(/json$/, "md"), REPORTS), "utf8");
const RUNS = [
  ["claude-first", claude, claudeTable],
  ["free", report, table],
] as const;

test.use(signedOut);

test("/ opens without a session and sends nothing to the API routes", async ({ page }) => {
  const api: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) api.push(request.url());
  });
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "Ask a company's annual report. Get an answer you can check.",
  );
  expect(api).toEqual([]);
});

test("/ needs no API: it renders while the API is off, with no detour to the demo", async ({ page }) => {
  const response = await page.goto(`${OFFLINE}/`);
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL(`${OFFLINE}/`);
  await expect(page.locator("#results tbody tr")).toHaveCount(
    resultRows(claudeTable).length + resultRows(table).length,
  );
  await expect(page.getByTestId("demo-banner")).toHaveCount(0);
});

test("the header's and the hero's links lead where they say", async ({ page }) => {
  await page.goto("/");
  const header = page.getByRole("banner");
  const links: [string, string][] = [
    ["How it works", "#how"],
    ["Results", "#results"],
    ["Architecture", "#architecture"],
    ["GitHub", "https://github.com/kwnhyk04/filing-lens"],
    ["Open the demo", "/demo"],
  ];
  for (const [name, href] of links) {
    await expect(header.getByRole("link", { name, exact: true })).toHaveAttribute("href", href);
  }
  for (const id of ["how", "results", "architecture"]) await expect(page.locator(`section#${id}`)).toHaveCount(1);
  await expect(page.getByRole("link", { name: "Read sample answers, no sign-in" })).toHaveAttribute("href", "/demo");
  await page.getByRole("link", { name: "Try the live demo" }).click();
  await expect(page).toHaveURL("/login?next=%2Fask");
  await signIn(page);
  await expect(page).toHaveURL("/ask");
  await expect(page.getByRole("heading", { level: 1, name: "Ask" })).toBeVisible();
});

test("the evaluation's tables, date, models and notes are the newest reports'", async ({ page }) => {
  await page.goto("/");
  const results = page.locator("#results");
  for (const [id, run, markdown] of RUNS) {
    const block = page.locator(`#results-${id}`);
    const rows = await block
      .locator("tbody tr")
      .evaluateAll((trs) => trs.map((tr) => [...(tr as HTMLTableRowElement).cells].map((cell) => cell.textContent?.trim())));
    expect(rows).toEqual(resultRows(markdown).map((row) => [row.label, row.target, row.result, row.status]));
    for (const text of [run.config.primary, `thinking ${run.config.thinking}`, run.config.router]) {
      await expect(block).toContainText(text);
    }
  }
  const { config, judge_calibration: judge } = report;
  const texts = [
    `${report.records.answer.length} questions`,
    evalDate(report.created_at),
    config.judge,
    "cross-checked blind by a second model; no human spot check in v2",
    `Cohen's kappa ${judge.kappa.toFixed(2)}`,
    `rests on ${report.metrics.retrieval["recall@10"].n} questions`,
  ];
  for (const text of texts) await expect(results).toContainText(text);
  await expect(results).toContainText(new RegExp(`labels written by ${judge.labeler}`, "i"));
  const how = page.locator("#how");
  await expect(how).toContainText(`${report.index.chunks.toLocaleString("en-US")} passages`);
  await expect(how).toContainText(`top ${config.rerank_candidates}`);
});

test("the hero's counts and its sample answer are the demo snapshot's", async ({ page }) => {
  await page.goto("/");
  const hero = page.locator(".hero");
  await expect(hero).toContainText(`${snapshot.companies.length} companies`);
  await expect(hero).toContainText(`${snapshot.answers.length} saved sample answers`);
  const sample = snapshot.answers.find((item) => item.id === SAMPLE);
  if (!sample) throw new Error(`${SAMPLE} is not in the snapshot`);
  const card = hero.getByRole("figure");
  await expect(card).toContainText(sample.question);
  await expect(card.locator(".answer-text")).toHaveText(sample.answer.answer);
  await expect(card).toContainText(sample.answer.citations[0].quote);
  await expect(card.getByRole("link", { name: /^Source 1: / })).toHaveAttribute("href", "#sample-source-1");
  await expect(card.locator("#sample-source-1")).toBeVisible();
});

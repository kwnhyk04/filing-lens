// The public landing page: no session, no API, its links, the theme, and every figure from the newest
// official eval report and the demo snapshot, both read here from disk, so a figure typed into the page
// fails. The hero's still is plain HTML; its moving story and three.js come after the load, on a desktop.
import { readdirSync, readFileSync } from "node:fs";

import type { Page } from "@playwright/test";

import type { Snapshot } from "../lib/demo.ts";
import { comparisonRows, EVIDENCE, evalDate, modelName, resultRows, sourceLink } from "../lib/landing.ts";
import { softwareRenderer } from "../lib/motion.ts";
import { heroStories, heroStory, QUOTE } from "../lib/story.ts";
import { LIVE, OFFLINE, snapshot } from "./env.ts";
import { audit, expect, noSidewaysScroll, signedOut, signIn, test } from "./fixtures.ts";

const REPORTS = new URL("../../evals/reports/", import.meta.url);
/** The newest official report of one kind, with its table: each kind is dated by its own run. */
function newestReport(kind: RegExp) {
  const name = readdirSync(REPORTS)
    .filter((file) => kind.test(file))
    .sort()
    .at(-1);
  if (!name) throw new Error(`No official report in evals/reports matches ${kind}`);
  return [JSON.parse(readFileSync(new URL(name, REPORTS), "utf8")), readFileSync(new URL(name.replace(/json$/, "md"), REPORTS), "utf8")] as const;
}
const [report, table] = newestReport(/^\d{4}-\d{2}-\d{2}\.json$/);
// The newest Claude-first run, the page's first column, which can be newer than the free-only run above.
const [claude, claudeTable] = newestReport(/^\d{4}-\d{2}-\d{2}-claude-first\.json$/);
const RUNS = [
  ["claude-first", claude, claudeTable],
  ["free", report, table],
] as const;
const demo = JSON.parse(readFileSync(new URL("../demo/snapshot.json", import.meta.url), "utf8")) as Snapshot;
const story = heroStory(demo);
const saved = heroStory(demo, QUOTE);
const REPO = "https://github.com/kwnhyk04/filing-lens";
const NOTE = `When the live backend is offline, the site serves ${snapshot.answers.length} saved sample answers.`;

/** The hero's main button leads to the demo, and its note says what the site serves while the API is off. */
async function heroOffersTheDemo(page: Page) {
  const hero = page.locator(".hero");
  await expect(hero.getByRole("link", { name: "Open the demo", exact: true })).toHaveAttribute("href", "/demo");
  await expect(hero).toContainText(NOTE);
}

// Reduced motion keeps every test on the still except the WebGL one, which asserts what this browser's
// renderer calls for: the moving story on a graphics card, the still on a software renderer (CI's runners).
test.use({ ...signedOut, reducedMotion: "reduce" });

type Script = { three: boolean; membrane: boolean; afterLoad: boolean };

/** Every script the page fetches: whether it holds three.js or the hero's membrane, and if it came after load. */
function watchScripts(page: Page): Script[] {
  const seen: Script[] = [];
  let loaded = false;
  page.on("load", () => {
    loaded = true;
  });
  page.on("response", async (response) => {
    if (response.request().resourceType() !== "script") return;
    const afterLoad = loaded;
    const body = await response.text().catch(() => "");
    // Strings that survive minifying: three.js's own log prefix, and a uniform of the membrane's shader.
    seen.push({ three: body.includes("THREE.WebGLRenderer"), membrane: body.includes("uCellA"), afterLoad });
  });
  return seen;
}

test("/ opens without a session and sends nothing to the API routes", async ({ page }) => {
  const api: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) api.push(request.url());
  });
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveAccessibleName("Every answer. Straight from the filing.");
  expect(api).toEqual([]);
});

test("/ needs no API: it renders while the API is off, with no detour to the demo", async ({ page }) => {
  const response = await page.goto(`${OFFLINE}/`);
  expect(response?.status()).toBe(200);
  await expect(page).toHaveURL(`${OFFLINE}/`);
  await expect(page.locator("#results tbody tr")).toHaveCount(resultRows(table).length);
  await expect(page.getByTestId("demo-banner")).toHaveCount(0);
  await heroOffersTheDemo(page);
});

test("the header's links lead where they say, and Sign in comes back to Ask", async ({ page }) => {
  await page.goto("/");
  const header = page.getByRole("banner");
  const links: [string, string][] = [
    ["FilingLens", "/"],
    ["How it works", "#how"],
    ["Results", "#results"],
    ["Architecture", "#architecture"],
    ["GitHub", REPO],
    ["Sign in", "/login"],
    ["Open the demo", "/demo"],
  ];
  for (const [name, href] of links) {
    await expect(header.getByRole("link", { name, exact: true })).toHaveAttribute("href", href);
  }
  for (const id of ["how", "results", "architecture"]) await expect(page.locator(`section#${id}`)).toHaveCount(1);
  await header.getByRole("link", { name: "Sign in" }).click();
  await expect(page).toHaveURL("/login");
  await signIn(page);
  await expect(page).toHaveURL("/ask");
  await expect(page.getByRole("heading", { level: 1, name: "Ask" })).toBeVisible();
});

/** Each cell of the results' rows as it reads on screen: what CSS hides at this width is left out. */
const shownRows = (page: Page) =>
  page
    .locator("#results tbody tr")
    .evaluateAll((trs) => trs.map((tr) => [...(tr as HTMLTableRowElement).cells].map((cell) => cell.innerText.replace(/\s+/g, " ").trim())));

/** The table's rows as a desktop shows them: the metric, its target, then each run's value and badge. */
const tableRows = () =>
  comparisonRows(claudeTable, table).map((row) => [
    row.label,
    row.target,
    `${row.claude.result} ${row.claude.status}`,
    `${row.free.result} ${row.free.status}`,
  ]);

test("the evaluation's one comparison table, its runs' models and dates, and its notes are the newest reports'", async ({ page }) => {
  await page.goto("/");
  const results = page.locator("#results");
  await expect(results.locator("table")).toHaveCount(1);
  expect(await shownRows(page)).toEqual(tableRows());
  const head = results.locator("thead");
  await expect(head.locator("th")).toHaveText([/^Metric/, /^Target/, /^Claude first/, /^Free models only/]);
  for (const [, run] of RUNS) {
    await expect(head).toContainText(`${modelName(run.config.primary)} · ${evalDate(run.created_at)}`);
    for (const text of [run.config.primary, `thinking ${run.config.thinking}`, run.config.router]) {
      await expect(results).toContainText(text);
    }
  }
  const { config, judge_calibration: judge } = report;
  const texts = [
    `${report.records.answer.length} questions`,
    `Claude first on ${evalDate(claude.created_at)}, the free models on ${evalDate(report.created_at)}`,
    config.judge,
    "cross-checked blind by a second model; no human spot check in v2",
    `Cohen's kappa ${judge.kappa.toFixed(2)}`,
    `rests on ${report.metrics.retrieval["recall@10"].n} questions`,
  ];
  // The columns' answer prompts differ until the free models run again, and the page must say so only then.
  if (claude.prompts.answer_system !== report.prompts.answer_system) texts.push("The free models' run predates the answer prompt Claude first used.");
  for (const text of texts) await expect(results).toContainText(text);
  await expect(results).toContainText(new RegExp(`labels written by ${judge.labeler}`, "i"));
  const how = page.locator("#how");
  await expect(how).toContainText(`${report.index.chunks.toLocaleString("en-US")} passages`);
  await expect(how).toContainText(`top ${config.rerank_candidates}`);
});

test("the Sonnet note: the dev split's figures from each arm's judged report, and which split they are", async ({ page }) => {
  const dev = (stamp: string) => JSON.parse(readFileSync(new URL(`runs/${stamp}-answer-dev-full-claude-first.json`, REPORTS), "utf8"));
  const [haiku, off, adaptive] = ["20261103T175043Z", "20261103T175921Z", "20261104T000849Z"].map(dev);
  expect([haiku, off, adaptive].map((run) => run.config.primary)).toEqual(["anthropic:claude-haiku-5-5", "anthropic:claude-sonnet-5-5", "anthropic:claude-sonnet-5-5"]);
  expect([off, adaptive].map((run) => run.config.thinking.split(",")[0])).toEqual(["between_tools", "adaptive"]);
  const precision = (run: typeof haiku) => run.metrics.answer.citation_precision.value.toFixed(3);
  const cost = (run: typeof haiku) => `$${run.metrics.answer.cost_usd.value.toFixed(4)}`;
  await page.goto("/");
  const note = page.getByTestId("sonnet-note");
  await expect(note).toHaveText(
    `Claude Sonnet 5.5 was measured too, on the ${haiku.records.answer.length} dev questions, not this test set: citation precision ${precision(off)} with thinking off and ${precision(adaptive)} with adaptive thinking against Haiku's ${precision(haiku)}, at ${cost(off)} and ${cost(adaptive)} a query against ${cost(haiku)}. Haiku stayed; see the measured decision.`,
  );
  await expect(note.getByRole("link", { name: "the measured decision" })).toHaveAttribute("href", /evals\/README\.md$/);
});

// Below 40rem each metric is a card, after FreightAudit's landing: its name, its target at the top right, then a
// line per run naming the run, its answer model and date, over the value and its badge.
const RUN_LABELS = [
  ["Claude first", claude],
  ["Free models only", report],
].map(([name, run]) => `${name}, ${modelName(run.config.primary)}, ${evalDate(run.created_at)}`);

/** Whatever in the results' cards leaves its card or the screen, or runs past its own box. */
const cutOff = (page: Page) =>
  page.locator("#results tbody tr").evaluateAll((cards) =>
    cards.flatMap((card) => {
      const box = card.getBoundingClientRect();
      const out = box.left < 0 || box.right > innerWidth ? [`card: ${card.textContent}`] : [];
      for (const part of [card, ...card.querySelectorAll("*")]) {
        const r = part.getBoundingClientRect();
        if (!r.width && !r.height) continue; // not shown at this width
        const leaves = r.left < box.left - 0.5 || r.right > box.right + 0.5 || r.top < box.top - 0.5 || r.bottom > box.bottom + 0.5;
        if (leaves || (part.clientWidth > 0 && part.scrollWidth > part.clientWidth + 1)) out.push(part.textContent ?? "");
      }
      return out;
    }),
  );

for (const width of [390, 430]) {
  test.describe(`the evaluation results at ${width} px`, () => {
    test.use({ viewport: { width, height: 932 }, isMobile: true, hasTouch: true });

    test("a card per metric: its target at the top right, then a line per run with its name, model and date, the value and badge", async ({ page }) => {
      await page.goto("/");
      const rows = comparisonRows(claudeTable, table);
      expect(await shownRows(page)).toEqual(
        rows.map((row) => [
          row.label,
          `Target ${row.target}`,
          `${RUN_LABELS[0]} ${row.claude.result} ${row.claude.status}`,
          `${RUN_LABELS[1]} ${row.free.result} ${row.free.status}`,
        ]),
      );
      const cards = await page.locator("#results tbody tr").evaluateAll((trs) =>
        trs.map((tr) => [tr, ...(tr as HTMLTableRowElement).cells].map((part) => part.getBoundingClientRect().toJSON() as DOMRect)),
      );
      for (const [card, name, target, ...runs] of cards) {
        expect(Math.abs(target.top - name.top)).toBeLessThan(2); // level with the name
        expect(target.left).toBeGreaterThanOrEqual(name.right); // on its right
        expect(card.right - target.right).toBeLessThan(20); // at the card's right edge, inside its padding
        let above = Math.max(name.bottom, target.bottom);
        for (const run of runs) {
          expect(run.top).toBeGreaterThanOrEqual(above - 1); // a line of its own, under the one before
          expect(Math.abs(run.left - name.left)).toBeLessThan(1);
          above = run.bottom;
        }
      }
      expect(await cutOff(page)).toEqual([]);
      await noSidewaysScroll(page);
      const region = page.getByRole("region", { name: "Results by metric" });
      expect(await region.evaluate((el) => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(0);
    });
  });
}

test("at 1440 px the results stay a table: its column heads show, each metric a row of level cells, no card labels", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const results = page.locator("#results");
  for (const head of await results.locator("thead th").all()) {
    await expect(head).toBeVisible();
    expect((await head.boundingBox())!.height).toBeGreaterThan(20);
  }
  expect(await shownRows(page)).toEqual(tableRows());
  const levels = await results
    .locator("tbody tr")
    .evaluateAll((trs) => trs.map((tr) => new Set([...(tr as HTMLTableRowElement).cells].map((cell) => Math.round(cell.getBoundingClientRect().top))).size));
  expect(levels).toEqual(levels.map(() => 1));
});

test("the hero's scope and story are the demo snapshot's: x12's question, passages, answer and check", async ({ page }) => {
  await page.goto("/");
  const hero = page.locator(".hero");
  await expect(hero.locator(".hero-lead")).toHaveText(
    `Ask about the 10-K filings of ${snapshot.companies.length} large US companies. FilingLens finds the passages and answers with citations you can check.`,
  );
  await heroOffersTheDemo(page);
  const still = hero.getByTestId("story-still");
  await expect(still).toContainText(story.question);
  await expect(still).toContainText(story.reading.join(" · "));
  await expect(still.locator(".answer-text")).toHaveText(story.answer.answer);
  for (const passage of story.passages) {
    const card = still.locator(`#hero-source-${passage.n}`);
    await expect(card).toContainText(passage.label);
    await expect(card).toContainText(passage.quote);
    // x12 cites its first passage twice, so each of its links must lead there.
    const links = still.getByRole("link", { name: `Source ${passage.n}: ${passage.label}` });
    expect(await links.count()).toBeGreaterThan(0);
    for (const link of await links.all()) await expect(link).toHaveAttribute("href", `#hero-source-${passage.n}`);
  }
  for (const check of story.checks) await expect(still).toContainText(check.text);
  await expect(hero).toContainText("A saved answer from golden v1's test run, as the demo shows it.");
});

test("the overview: another saved answer and its passage, two figures from the snapshot and both reports, #42, and the three jobs", async ({ page }) => {
  await page.goto("/");
  const overview = page.locator("section#overview");
  await expect(overview.getByRole("heading", { level: 2 })).toHaveText("At a glance.");
  // The headline and the line under it, with no label above them.
  await expect(overview.locator(".overview-head > *")).toHaveText([
    "At a glance.",
    "A sourced answer, tested numbers, and the newest feature.",
  ]);
  expect(saved.filing).not.toBe(story.filing);
  await expect(overview).toContainText(saved.question);
  await expect(overview.locator("blockquote .answer-text")).toHaveText(saved.answer.answer);
  for (const passage of saved.passages) {
    await expect(overview.locator(`#overview-source-${passage.n}`)).toContainText(passage.label);
    const links = overview.getByRole("link", { name: `Source ${passage.n}: ${passage.label}` });
    expect(await links.count()).toBeGreaterThan(0);
    for (const link of await links.all()) await expect(link).toHaveAttribute("href", `#overview-source-${passage.n}`);
  }
  // The snapshot's indexed filings, one per company; numeric exact match, the same in both official runs.
  const filings = snapshot.companies.reduce((sum, company) => sum + company.filings.edges.length, 0);
  expect(filings).toBe(snapshot.companies.length);
  const exact = claude.metrics.answer.numeric_exact_match;
  for (const [, run] of RUNS) expect(run.metrics.answer.numeric_exact_match).toMatchObject({ value: exact.value, n: exact.n });
  const figure = (label: string) => overview.locator(".overview-figure").filter({ hasText: label });
  await expect(figure("Filings indexed").locator(".overview-value")).toHaveText(String(filings));
  await expect(figure("Filings indexed")).toContainText("One 10-K from each company");
  await expect(figure("Exact numbers").locator(".overview-value")).toHaveText(`${Math.round(exact.value * 100)}%`);
  await expect(figure("Exact numbers")).toContainText(
    `${Math.round(exact.value * exact.n)} of ${exact.n} numeric test questions within 0.5%, in both official runs`,
  );
  await expect(overview.getByRole("heading", { level: 3, name: "Recent questions" })).toBeVisible();
  await expect(overview.getByRole("link", { name: "Read the pull request" })).toHaveAttribute("href", `${REPO}/pull/42`);
  await expect(overview.locator(".overview-jobs dt")).toHaveText(["Ask", "Cite", "Check"]);
});

test("How an answer is made: four numbered steps joined by a line, each an icon, a title, one line and its points", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  const steps = page.locator("#how ol.how-steps > li");
  await expect(steps.locator("h3")).toHaveText(["Route", "Retrieve", "Answer", "Check"]);
  await expect(steps.locator(".step-number")).toHaveText(["1", "2", "3", "4"]);
  for (const step of await steps.all()) {
    await expect(step.locator(".step-icon[aria-hidden='true'] svg")).toHaveCount(1);
    await expect(step.locator(".step-line")).toHaveCount(1);
    const points = await step.locator("ul > li").count();
    expect(points).toBeGreaterThanOrEqual(1);
    expect(points).toBeLessThanOrEqual(3);
  }
  for (const fact of ["XBRL facts first", "word for word", "redone once", "a refusal, not a guess"]) {
    await expect(page.locator("#how")).toContainText(fact);
  }
  // A desktop shows one row, each number joined by a line to the one before; a phone stacks them, with no line.
  const boxes = () => steps.evaluateAll((items) => items.map((item) => item.getBoundingClientRect()).map(({ top, left }) => ({ top: Math.round(top), left: Math.round(left) })));
  const lines = () =>
    steps.evaluateAll((items) =>
      items.map((item) => getComputedStyle(item, "::before")).map((line) => line.content !== "none" && line.display !== "none"),
    );
  expect(new Set((await boxes()).map((box) => box.top)).size).toBe(1);
  expect(await lines()).toEqual([false, true, true, true]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(new Set((await boxes()).map((box) => box.left)).size).toBe(1);
  expect(await lines()).toEqual([false, false, false, false]);
  await noSidewaysScroll(page);
});

test("How an answer is made is centred: its heading, the row of steps, each number over its card's middle", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/");
  const how = page.locator("#how");
  const [section, title, list] = await Promise.all([how, how.locator("h2"), how.locator("ol.how-steps")].map((part) => part.boundingBox()));
  const middle = (box: { x: number; width: number }) => box.x + box.width / 2;
  expect(Math.abs(middle(title!) - middle(section!))).toBeLessThan(2);
  expect(Math.abs(middle(list!) - middle(section!))).toBeLessThan(2);
  for (const step of await how.locator("ol.how-steps > li").all()) {
    const [card, number] = await Promise.all([step.boundingBox(), step.locator(".step-number").boundingBox()]);
    expect(Math.abs(middle(number!) - middle(card!))).toBeLessThan(2);
  }
  const heights = await how.locator("ol.how-steps > li").evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().height)));
  expect(new Set(heights).size).toBe(1);
  expect(await how.locator("ol.how-steps > li").first().evaluate((item) => getComputedStyle(item).textAlign)).toBe("left");
});

test("Architecture: each claim says what it means and links the files that prove it, one a line, the stack under it", async ({ page }) => {
  await page.goto("/");
  const section = page.locator("#architecture");
  await expect(section.locator(".evidence dt")).toHaveText(EVIDENCE.map((item) => item.claim));
  for (const [i, item] of EVIDENCE.entries()) {
    const entry = section.locator(".evidence dd").nth(i);
    await expect(entry).toContainText(item.line);
    const links = entry.locator("a");
    await expect(links).toHaveText(item.paths);
    for (const [j, path] of item.paths.entries()) await expect(links.nth(j)).toHaveAttribute("href", sourceLink(path));
    const tops = await links.evaluateAll((all) => all.map((link) => Math.round(link.getBoundingClientRect().top)));
    expect(new Set(tops).size).toBe(tops.length); // one file a line
  }
  await expect(section.locator("ul.chips li").first()).toHaveText("Python");
});

test("the theme toggle keeps Light or Dark in a cookie the server reads, and System clears it", async ({ page, context }) => {
  await page.goto("/");
  const html = page.locator("html");
  await expect(html).not.toHaveAttribute("data-theme");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(244, 245, 242)");
  await page.getByRole("radio", { name: "Dark" }).check();
  await expect(html).toHaveAttribute("data-theme", "dark");
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(18, 21, 20)");
  expect((await context.cookies()).find((cookie) => cookie.name === "fl-theme")?.value).toBe("dark");
  // Rendered dark on the server, so nothing flashes: the HTML itself carries the theme.
  expect(await (await page.request.get("/demo")).text()).toMatch(/<html[^>]* data-theme="dark"/);
  await page.reload();
  await expect(page.getByRole("radio", { name: "Dark" })).toBeChecked();
  await page.getByRole("radio", { name: "System" }).check();
  await expect(html).not.toHaveAttribute("data-theme");
  expect((await context.cookies()).some((cookie) => cookie.name === "fl-theme")).toBe(false);
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, reducedMotion: "no-preference" });

  test("the section links, the theme and Sign in fold into a menu", async ({ page }) => {
    await page.goto("/");
    const header = page.getByRole("banner");
    const menu = header.getByRole("button", { name: "Menu" });
    await expect(header.getByRole("link", { name: "Open the demo" })).toBeVisible();
    await expect(header.getByRole("link", { name: "Results" })).toBeHidden();
    await menu.click();
    await expect(menu).toHaveAttribute("aria-expanded", "true");
    await expect(header.getByRole("link", { name: "Results" })).toBeVisible();
    await expect(header.getByRole("link", { name: "Sign in" })).toBeVisible();
    await expect(header.getByRole("group", { name: "Theme" })).toBeVisible();
    await noSidewaysScroll(page);
    await page.keyboard.press("Escape");
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await expect(menu).toBeFocused();
    await menu.click();
    await header.getByRole("link", { name: "Results" }).click();
    await expect(menu).toHaveAttribute("aria-expanded", "false");
    await expect(page).toHaveURL(/#results$/);
  });

  test("a phone keeps the still: no three.js, no membrane, no canvas", async ({ page }) => {
    const scripts = watchScripts(page);
    await page.goto("/");
    await page.waitForTimeout(3_000); // past the idle callback's 2 s deadline
    expect(scripts.filter((script) => script.three || script.membrane)).toEqual([]);
    await expect(page.locator(".hero canvas")).toHaveCount(0);
    await expect(page.getByTestId("story-still")).toBeVisible();
    await noSidewaysScroll(page);
  });
});

test.describe("with reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("a desktop keeps the still: no three.js, no membrane, no canvas", async ({ page }) => {
    const scripts = watchScripts(page);
    await page.goto("/");
    await page.waitForTimeout(3_000);
    expect(scripts.filter((script) => script.three || script.membrane)).toEqual([]);
    await expect(page.locator(".hero canvas")).toHaveCount(0);
    await expect(page.getByTestId("story-still")).toBeVisible();
  });
});

/** Which renderer draws this browser's WebGL: Playwright's bundled shell and CI's runners have SwiftShader only;
    headless Edge (E2E_CHANNEL=msedge) draws on this PC's graphics card. */
const rendererOf = (page: Page) =>
  page.evaluate(() => {
    const gl = document.createElement("canvas").getContext("webgl");
    const info = gl?.getExtension("WEBGL_debug_renderer_info");
    return gl ? String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : "";
  });

/** The moving story once it stands in for the still. A software renderer keeps the still (the test below checks
    that), so on one these tests are skipped: run them with E2E_CHANNEL=msedge on a graphics card. */
async function movingStory(page: Page) {
  // Every WebGL draw, the membrane's and the field's, counted on window.draws.
  await page.addInitScript(() => {
    const counted = window as unknown as { draws: number };
    counted.draws = 0;
    for (const context of [WebGLRenderingContext, WebGL2RenderingContext]) {
      for (const name of ["drawArrays", "drawElements"] as const) {
        const draw = context.prototype[name] as (...args: unknown[]) => void;
        Object.defineProperty(context.prototype, name, {
          value(this: unknown, ...args: unknown[]) {
            counted.draws += 1;
            return draw.apply(this, args);
          },
        });
      }
    }
  });
  await page.goto("/");
  const renderer = await rendererOf(page);
  test.skip(!renderer || softwareRenderer(renderer), "the moving story needs WebGL on a graphics card");
  await expect(page.locator(".hero")).toHaveAttribute("data-live", "on", { timeout: 15_000 });
  return page.locator(".story-live");
}

const draws = (page: Page) => page.evaluate(() => (window as unknown as { draws: number }).draws);
const stories = heroStories(demo);

test.describe("on a desktop", () => {
  test.use({ reducedMotion: "no-preference" });

  test("WebGL on a graphics card plays the story after the load; a software renderer keeps the still", async ({ page }) => {
    const scripts = watchScripts(page);
    const elsewhere: string[] = [];
    page.on("request", (request) => {
      if (!request.url().startsWith(LIVE) && !request.url().startsWith("data:")) elsewhere.push(request.url());
    });
    await page.goto("/");
    const hero = page.locator(".hero");
    const renderer = await rendererOf(page);
    if (!renderer || softwareRenderer(renderer)) {
      await expect(hero).toHaveAttribute("data-motion", "still", { timeout: 15_000 });
      expect(scripts.filter((script) => script.three || script.membrane)).toEqual([]);
      await expect(page.locator(".hero canvas")).toHaveCount(0);
      await expect(page.getByTestId("story-still")).toBeVisible();
      expect(elsewhere).toEqual([]);
      return;
    }
    await expect(hero).toHaveAttribute("data-motion", "live", { timeout: 15_000 });
    await expect(hero).toHaveAttribute("data-live", "on", { timeout: 15_000 });
    await expect(page.locator(".hero-field canvas")).toHaveCount(1, { timeout: 15_000 });
    const heavy = scripts.filter((script) => script.three || script.membrane);
    expect(heavy.some((script) => script.three)).toBe(true);
    expect(heavy.some((script) => script.membrane)).toBe(true);
    expect(heavy.every((script) => script.afterLoad)).toBe(true);
    expect(elsewhere).toEqual([]);
    // The still leaves the reading order once the moving story stands in for it.
    await expect(page.getByTestId("story-still")).toHaveAttribute("aria-hidden", "true");
    const pause = hero.getByRole("button", { name: "Pause motion" });
    await pause.click();
    await expect(hero.getByRole("button", { name: "Resume motion" })).toHaveAttribute("aria-pressed", "true");
    await audit(page);
  });

  test("the story moves on to the next saved answer once the first has held for about 7 s", async ({ page }) => {
    test.setTimeout(120_000);
    const live = await movingStory(page);
    await expect(live).toContainText(stories[0].question);
    await expect(live).toHaveAttribute("data-beat", "5", { timeout: 45_000 }); // x12's answer and check are in
    const done = Date.now();
    await expect(live).toContainText(stories[1].question, { timeout: 30_000 });
    expect(Date.now() - done).toBeGreaterThan(6_000);
    // The next answer plays as the first did, and the controls are the same ones.
    await expect(live).not.toContainText(stories[0].question);
    await expect(live).toHaveAttribute("data-beat", "2", { timeout: 15_000 });
    await page.locator(".hero").getByRole("button", { name: "Replay" }).click();
    await expect(live).toHaveAttribute("data-beat", "0");
    await expect(live).toContainText(stories[1].question); // Replay starts the current answer again
  });

  test("hovering the card, or keyboard focus inside it, pauses the story; leaving it goes on", async ({ page }) => {
    test.setTimeout(90_000);
    const live = await movingStory(page);
    await expect(live).toHaveAttribute("data-beat", "2", { timeout: 20_000 });
    await live.hover();
    await expect(live).toHaveAttribute("data-moving", "false");
    const beat = await live.getAttribute("data-beat");
    await page.waitForTimeout(4_000); // longer than any one beat
    await expect(live).toHaveAttribute("data-beat", beat ?? "");
    await page.mouse.move(5, 5);
    await expect(live).toHaveAttribute("data-moving", "true");
    await expect(live).toHaveAttribute("data-beat", "5", { timeout: 45_000 });
    await live.getByRole("link").first().focus(); // a citation in the answer
    await expect(live).toHaveAttribute("data-moving", "false");
    await page.waitForTimeout(9_000); // past the 7 s hold: still the same answer
    await expect(live).toContainText(stories[0].question);
    await page.locator(".hero").getByRole("button", { name: "Replay" }).focus();
    await expect(live).toHaveAttribute("data-moving", "true");
  });

  test("no floating label ever crosses another, through each answer's find beat, round the whole loop", async ({ page }) => {
    test.setTimeout(150_000);
    await page.setViewportSize({ width: 1440, height: 900 });
    await movingStory(page);
    // Every frame, each visible thing's label box against every other's, until each answer has reached its answer beat.
    const crossings = await page.evaluate(
      (count) =>
        new Promise<string[]>((resolve) => {
          const found = new Set<string>();
          let answered = 0, last = "";
          const tick = () => {
            const beat = document.querySelector(".story-live")?.getAttribute("data-beat") ?? "";
            if (beat === "4" && last !== "4") answered++;
            last = beat;
            const labels = [...document.querySelectorAll<HTMLElement>(".pb-thing")]
              .filter((thing) => thing.dataset.empty !== "true" && Number(thing.style.opacity || 0) > 0.05)
              .map((thing) => ({ name: thing.querySelector("b")?.textContent ?? "", box: thing.querySelector(".pb-thing-label")!.getBoundingClientRect() }));
            labels.forEach((a, i) =>
              labels.slice(i + 1).forEach((b) => {
                const x = Math.min(a.box.right, b.box.right) - Math.max(a.box.left, b.box.left);
                const y = Math.min(a.box.bottom, b.box.bottom) - Math.max(a.box.top, b.box.top);
                if (x > 0.5 && y > 0.5) found.add(`beat ${beat}: ${a.name} / ${b.name}`);
              }),
            );
            if (answered >= count) resolve([...found]);
            else requestAnimationFrame(tick);
          };
          tick();
        }),
      stories.length,
    );
    expect(crossings).toEqual([]);
  });

  test("the story stops, and draws nothing, while the hero is scrolled away; back in view it goes on", async ({ page }) => {
    test.setTimeout(90_000);
    const live = await movingStory(page);
    await expect(live).toHaveAttribute("data-beat", "2", { timeout: 20_000 });
    await page.locator("#architecture").scrollIntoViewIfNeeded();
    await expect(live).toHaveAttribute("data-moving", "false");
    await page.waitForTimeout(1_000); // the last frames after the stop
    const beat = await live.getAttribute("data-beat");
    const before = await draws(page);
    await page.waitForTimeout(4_000);
    expect(await draws(page)).toBe(before);
    await expect(live).toHaveAttribute("data-beat", beat ?? "");
    await page.evaluate(() => window.scrollTo(0, 0));
    await expect(live).toHaveAttribute("data-moving", "true");
    await expect.poll(() => draws(page)).toBeGreaterThan(before);
  });
});

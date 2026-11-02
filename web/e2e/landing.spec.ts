// The public landing page: no session, no API, its links, the theme, and every figure from the newest
// official eval report and the demo snapshot, both read here from disk, so a figure typed into the page
// fails. The hero's still is plain HTML; its moving story and three.js come after the load, on a desktop.
import { readdirSync, readFileSync } from "node:fs";

import type { Page } from "@playwright/test";

import type { Snapshot } from "../lib/demo.ts";
import { evalDate, resultRows } from "../lib/landing.ts";
import { softwareRenderer } from "../lib/motion.ts";
import { heroStories, heroStory, QUOTE } from "../lib/story.ts";
import { LIVE, OFFLINE, snapshot } from "./env.ts";
import { audit, expect, noSidewaysScroll, signedOut, signIn, test } from "./fixtures.ts";

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
  await expect(page.locator("#results tbody tr")).toHaveCount(
    resultRows(claudeTable).length + resultRows(table).length,
  );
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

// Ask's stage, the live version of the landing hero: the field inside it, the question shown once, each part
// only when it is reported, Recent questions and Sources below. On a graphics card the moving stage plays over
// the same states; elsewhere (CI's software renderer, phones, reduced motion) the calm version stays.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { softwareRenderer } from "../lib/motion.ts";
import { question, snapshot } from "./env.ts";
import { ask, audit, expect, noSidewaysScroll, test } from "./fixtures.ts";

const N01 = question("n01");
const X04 = question("x04");
const EXAMPLES = snapshot.answers.filter((item) => !item.answer.refused).map((item) => item.question).slice(0, 4);
const READING = "Reading the filings…";
const stage = (page: Page) => page.locator(".stage");
const box = (page: Page) => page.getByLabel("Your question");

/** The WebGL renderer the page would draw with, or null without WebGL. */
const rendererOf = (page: Page) =>
  page.evaluate(() => {
    const gl = document.createElement("canvas").getContext("webgl");
    const info = gl?.getExtension("WEBGL_debug_renderer_info");
    return gl ? String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : null;
  });

test("empty: example questions as chips and the field inside the stage; Sources says what will appear there", async ({ page }) => {
  await page.goto("/ask");
  await expect(stage(page).getByTestId("samples").getByRole("button")).toHaveText(EXAMPLES);
  await expect(stage(page).getByLabel("Your question")).toHaveAttribute("placeholder", "Ask about a company's 10-K...");
  await expect(stage(page).getByRole("button", { name: "Ask", exact: true })).toBeVisible();
  await expect(page.getByTestId("sources-card")).toHaveText(/Sources for your answer appear here\./);
  await audit(page);
});

test("on send the question shows once, in the stage's bubble; the field clears; nothing is claimed while it reads", async ({ page }) => {
  const slow = `e2e: slow ${randomUUID()}`; // the mock drafts it for about 3 s, then completes it as o02's refusal
  await page.goto("/ask");
  await box(page).fill(slow);
  await box(page).press("Enter");
  await expect(stage(page).locator(".story-sent")).toHaveText(slow);
  await expect(box(page)).toHaveValue("");
  await expect(stage(page).getByText(READING)).toBeVisible();
  await expect(stage(page).getByRole("button", { name: "Answering…" })).toBeVisible();
  await expect(stage(page).locator(".stage-covered li")).toHaveCount(11); // the coverage list's filings, none lit
  await expect(stage(page).locator(".story-passages li, .card-filings li")).toHaveCount(0);
  await expect(page.getByTestId("draft")).toContainText("Still drafting.");
  await expect(page.getByTestId("answer")).toContainText("Not answered", { timeout: 15_000 });
  await expect(stage(page).getByText(READING)).toHaveCount(0);
  await expect(stage(page).getByRole("button", { name: "Ask", exact: true })).toBeVisible();
});

test("Enter sends and Shift+Enter starts a new line; under 3 characters nothing is sent", async ({ page }) => {
  const sent: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/answers") sent.push(request.postData() ?? "");
  });
  await page.goto("/ask");
  await box(page).pressSequentially("ab");
  await box(page).press("Enter");
  expect(await box(page).evaluate((element) => (element as HTMLTextAreaElement).validity.tooShort)).toBe(true);
  await expect(page.locator("#question-help")).toContainText("3 to 1,000 characters");
  await box(page).fill("");
  await box(page).pressSequentially("What was Apple's");
  await box(page).press("Shift+Enter");
  await box(page).pressSequentially("revenue?");
  await expect(box(page)).toHaveValue("What was Apple's\nrevenue?");
  expect(sent).toEqual([]);
  await box(page).press("Enter");
  await expect.poll(() => sent.length).toBe(1);
});

test("the answer fills the stage and its sources the Sources card; New question empties the stage; a recent question fills it again", async ({ page }) => {
  await ask(page, N01);
  await expect(stage(page).getByTestId("answer")).toContainText("416,161,000,000 USD");
  await expect(stage(page).getByTestId("read-as")).toBeVisible();
  await expect(stage(page).locator("[data-tone='check']")).toBeVisible();
  await expect(stage(page).locator(".story-passages li")).toHaveCount(1);
  await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
  await page.getByRole("button", { name: "New question" }).click();
  await expect(stage(page).locator(".story-sent")).toHaveCount(0);
  await expect(stage(page).getByTestId("samples")).toBeVisible();
  await expect(page.getByTestId("sources-card")).toHaveText(/Sources for your answer appear here\./);
  await page.getByTestId("recent").getByRole("button").filter({ hasText: N01 }).click();
  await expect(stage(page).locator(".story-sent")).toHaveText(N01);
  await expect(box(page)).toHaveValue("");
  await expect(page.getByTestId("stored")).toBeVisible();
});

test("Recent questions and Sources sit under the stage, 60 to 40 and top-aligned; under 1024 px Sources comes first", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/ask");
  const boxes = () =>
    Promise.all([stage(page), page.getByTestId("recent-card"), page.getByTestId("sources-card")].map((part) => part.boundingBox()));
  const [top, recent, sources] = await boxes();
  expect(recent!.y).toBeGreaterThan(top!.y + top!.height);
  expect(sources!.y).toBeCloseTo(recent!.y, 0);
  expect(sources!.x).toBeGreaterThan(recent!.x + recent!.width);
  expect(recent!.width / (recent!.width + sources!.width)).toBeCloseTo(0.6, 1);
  await page.setViewportSize({ width: 1000, height: 800 });
  const [, narrowRecent, narrowSources] = await boxes();
  expect(narrowSources!.y + narrowSources!.height).toBeLessThanOrEqual(narrowRecent!.y);
  await page.setViewportSize({ width: 390, height: 844 });
  await noSidewaysScroll(page);
});

test("from 64rem a long Sources card scrolls in itself, and nothing inside it stretches the page", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await ask(page, question("c12")); // four sources, two of them long passages
  await expect(page.getByTestId("sources-card").locator("#source-4 h4")).toContainText("TSLA");
  const sources = page.getByTestId("sources-card").locator(".sources");
  expect(await sources.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  // Its visually hidden text once stretched the page about 2,900 px past its end.
  expect(await page.evaluate(() => document.documentElement.scrollHeight - document.body.scrollHeight)).toBe(0);
});

test("a software renderer keeps the calm stage: no canvas and no moving parts", async ({ page }) => {
  await page.goto("/ask");
  const renderer = await rendererOf(page);
  test.skip(!!renderer && !softwareRenderer(renderer), "this checks the path without a graphics card");
  await expect(stage(page)).toHaveAttribute("data-motion", "still", { timeout: 15_000 });
  await expect(page.locator("canvas")).toHaveCount(0);
});

test.describe("on a desktop with a graphics card", () => {
  test.use({ reducedMotion: "no-preference" });

  async function moving(page: Page) {
    await page.goto("/ask");
    const renderer = await rendererOf(page);
    test.skip(!renderer || softwareRenderer(renderer), "the moving stage needs WebGL on a graphics card");
    await expect(stage(page)).toHaveAttribute("data-motion", "live", { timeout: 15_000 });
  }

  test("while it reads only covered filings float; with the sources only the cited one is pulled in, with its item", async ({ page }) => {
    test.setTimeout(60_000);
    await moving(page);
    await box(page).fill(`e2e: slow ${randomUUID()}`);
    await box(page).press("Enter");
    await expect(stage(page).getByText(READING)).toBeVisible();
    const things = page.locator(".stage .pb-thing:not([data-empty='true'])");
    await expect(things.filter({ hasNotText: "Filing" })).toHaveCount(0);
    await expect(things).toHaveCount(11);
    await expect(page.getByTestId("answer")).toBeVisible({ timeout: 15_000 });
    await page.getByRole("button", { name: "New question" }).click();
    await box(page).fill(X04);
    await box(page).press("Enter");
    await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AMZN");
    const cited = page.locator(".stage .pb-thing[data-kind='passage']");
    await expect(cited).toHaveCount(1);
    await expect(cited).toContainText("Item 1");
    await expect(cited).toContainText("AMZN 10-K FY2025");
  });

  test("the answer shows the moment the stream completes, never after an animation", async ({ page }) => {
    // Both times taken in the page: when the answer stream's last byte is read, and when the answer is on screen.
    // (Playwright's own end of a streamed response came 30 s late, or never, under the full suite's load.)
    await page.addInitScript(() => {
      const times: { ended?: number; shown?: number } = {};
      (window as unknown as { times: typeof times }).times = times;
      const original = window.fetch;
      window.fetch = async (...args: Parameters<typeof fetch>) => {
        const response = await original(...args);
        if (!String(args[0]).endsWith("/api/answers") || !response.body) return response;
        const reader = response.body.getReader();
        const body = new ReadableStream<Uint8Array>({
          async pull(controller) {
            const { done, value } = await reader.read();
            if (done) {
              times.ended = performance.now();
              controller.close();
            } else controller.enqueue(value);
          },
        });
        return new Response(body, { status: response.status, headers: response.headers });
      };
      new MutationObserver(() => {
        if (document.querySelector("[data-testid='answer']")) times.shown ??= performance.now();
      }).observe(document, { childList: true, subtree: true });
    });
    await moving(page);
    await box(page).fill(X04);
    await box(page).press("Enter");
    await expect(page.getByTestId("answer")).toBeVisible();
    const { ended, shown } = await page.evaluate(() => (window as unknown as { times: { ended: number; shown: number } }).times);
    expect(shown - ended).toBeLessThan(1_000);
  });
});

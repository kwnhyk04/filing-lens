// Ask's answer card, in the landing hero's look and order: it reads until the answer and its sources are both in,
// then shows Read as, the passages, the answer and the check, one by one where motion is allowed and all at once on
// a phone or under reduced motion. The same card holds a stored answer, an error, and each of the demo's saved
// answers; and the app around it: the theme switch in its header, Coverage as cards on a phone, and no WebGL anywhere.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { question, snapshot } from "./env.ts";
import { ask, audit, expect, noSidewaysScroll, partsSeen, test, watchParts } from "./fixtures.ts";

const N01 = question("n01");
const X04 = question("x04");
const card = (page: Page) => page.locator(".answer-card");
const arrived = (page: Page) => card(page).locator(".story-passages li, [data-tone='check'], .card-filings li");
const motionOf = (page: Page, selector: string) =>
  card(page).locator(selector).first().evaluate((element) => getComputedStyle(element).animationName);

/** Holds the sources lookup until `release` is called. */
async function holdSources(page: Page) {
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/sources", async (route) => {
    await held;
    await route.continue();
  });
  const looked = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/sources");
  return { looked, release: () => release() };
}

test("while FilingLens reads, the card holds the question and the reading line only, never a draft", async ({ page }) => {
  const slow = `e2e: slow ${randomUUID()}`; // the mock drafts it for about 3 s, then completes it as o02's refusal
  await ask(page, slow);
  await expect(card(page).locator(".story-sent")).toHaveText(slow);
  await expect(card(page).getByTestId("reading")).toContainText("Reading the filings…");
  await expect(page.getByTestId("draft")).toHaveCount(0);
  await expect(page.getByTestId("read-as")).toHaveCount(0);
  await expect(arrived(page)).toHaveCount(0);
  await expect(page.getByTestId("answer")).toHaveCount(0);
  await expect(page.getByTestId("answer")).toContainText("Not answered", { timeout: 15_000 });
  await expect(card(page).getByTestId("reading")).toHaveCount(0);
  await expect(page.getByTestId("read-as").getByRole("listitem")).toHaveText(["Out of scope"]);
  await expect(arrived(page)).toHaveCount(0); // a refusal cites and checks nothing
});

test("the answer waits for its sources, then its parts arrive one by one in the hero's order", async ({ page }) => {
  const sources = await holdSources(page);
  await ask(page, N01);
  await sources.looked; // the checked answer is in: its sources are being looked up
  await expect(card(page).getByTestId("reading")).toContainText("Reading the filings…");
  await expect(page.getByTestId("answer")).toHaveCount(0);
  await expect(page.getByTestId("read-as")).toHaveCount(0);
  await watchParts(page);
  sources.release();
  const row = card(page).locator(".story-passages li");
  await expect(row).toHaveCount(1);
  await expect(row.locator(".story-n")).toHaveText("1");
  await expect(row).toContainText("AAPL fact, Revenue from Contract with Customer, Excluding Assessed Tax, period ending 2025-09-27");
  await expect(row).toContainText("416,161,000,000 USD");
  await expect(card(page).locator(".card-filings li")).toHaveText(["AAPL 10-K FY2025"]);
  await expect(card(page).locator("[data-tone='check']")).toHaveText("Checked: 416,161,000,000 matches source 1.");
  await expect(page.getByTestId("answer")).toContainText("416,161,000,000 USD");
  await expect(card(page).getByTestId("reading")).toHaveCount(0);
  const seen = await partsSeen(page);
  expect(seen.read).toBeLessThan(seen.passages);
  expect(seen.passages).toBeLessThan(seen.answer);
  expect(seen.answer).toBeLessThan(seen.check);
  expect(seen.check).toBeLessThan(2_000);
  // Top to bottom in the same order, as the hero's panel.
  const [read, first, reply, check] = await Promise.all(
    [page.getByTestId("read-as"), row, card(page).locator(".story-reply"), card(page).locator("[data-tone='check']")].map((part) =>
      part.boundingBox(),
    ),
  );
  expect(first!.y).toBeGreaterThanOrEqual(read!.y + read!.height);
  expect(reply!.y).toBeGreaterThanOrEqual(first!.y + first!.height);
  expect(check!.y).toBeGreaterThanOrEqual(reply!.y + reply!.height);
});

test("an error sits in the card, under the question, and the field comes back", async ({ page }) => {
  await ask(page, "e2e: busy");
  await expect(card(page).locator(".story-sent")).toHaveText("e2e: busy");
  await expect(card(page).getByTestId("ask-error")).toContainText("The service is busy. Try again in 2 s.");
  await expect(page.getByTestId("draft")).toHaveCount(0);
  await expect(page.getByLabel("Your question")).toBeVisible();
  await audit(page);
});

test("what arrives moves in while motion is allowed; a stored answer from the list appears whole", async ({ page }) => {
  await ask(page, N01);
  await expect(card(page).locator(".story-passages li")).toHaveCount(1);
  await ask(page, X04);
  await expect(card(page).locator(".story-passages li")).toContainText("AMZN 10-K FY2025, Item 1");
  for (const part of [".story-passages li", ".card-filings li", "[data-tone='check']"]) {
    expect(await motionOf(page, part)).not.toBe("none");
  }
  await page.getByTestId("recent").getByRole("button").filter({ hasText: N01 }).click();
  await expect(page.getByTestId("stored")).toBeVisible();
  await expect(card(page).locator(".story-passages li")).toContainText("AAPL fact");
  for (const part of [".story-passages li", ".card-filings li", "[data-tone='check']", ".story-reply"]) {
    expect(await motionOf(page, part)).toBe("none");
  }
});

/** With motion off, every part shows in the same commit, and nothing in the card moves. */
async function allAtOnce(page: Page) {
  const sources = await holdSources(page);
  await ask(page, X04);
  await sources.looked;
  await watchParts(page);
  sources.release();
  await expect(card(page).locator(".story-passages li")).toHaveCount(1);
  const seen = await partsSeen(page);
  const times = [seen.read, seen.passages, seen.answer, seen.check];
  expect(Math.max(...times) - Math.min(...times)).toBeLessThan(50);
  for (const part of [".story-passages li", ".card-filings li", "[data-tone='check']", ".story-reply", "[data-tone='read']"]) {
    expect(await motionOf(page, part)).toBe("none");
  }
}

test.describe("with reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("every part shows at once, in the same order, and nothing in the card moves", async ({ page }) => {
    await allAtOnce(page);
  });
});

test("with reduced motion, no canvas and no WebGL context on Ask, Coverage or the demo", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" }); // a desktop on a graphics card may load Ask's moving stage
  await page.addInitScript(() => {
    const scope = window as unknown as { contexts: number };
    const original = HTMLCanvasElement.prototype.getContext;
    scope.contexts = 0;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, ...args: Parameters<typeof original>) {
      scope.contexts++;
      return original.apply(this, args);
    } as typeof original;
  });
  await ask(page, X04);
  await expect(card(page).locator(".story-passages li")).toHaveCount(1);
  for (const path of ["", "/coverage", "/demo"]) {
    if (path) await page.goto(path);
    await expect(page.locator("canvas")).toHaveCount(0);
    expect(await page.evaluate(() => (window as unknown as { contexts: number }).contexts)).toBe(0);
  }
});

test("the demo shows each saved answer in the card, at rest: its question, reading, answer, passages and filing", async ({ page }) => {
  await page.goto("/demo");
  for (const item of snapshot.answers) {
    const saved = page.locator(`#q-${item.id} .answer-card`);
    await expect(saved).toHaveAttribute("data-still", "true");
    await expect(saved.locator(".story-sent")).toHaveText(item.question);
    await expect(saved.locator(".answer-text")).toHaveText(item.answer.answer);
    await expect(saved.locator(".story-passages li")).toHaveCount(item.answer.citations.length);
    await expect(saved.locator(".card-filings li")).toHaveCount(item.answer.refused ? 0 : 1 + Number(item.id === "c02"));
  }
});

test("the app's header carries the landing's theme switch, and Dark stays on every page", async ({ page }) => {
  for (const path of ["/ask", "/coverage", "/demo"]) {
    await page.goto(path);
    await expect(page.getByRole("banner").getByRole("group", { name: "Theme" })).toBeVisible();
  }
  await page.goto("/ask");
  await page.getByRole("banner").getByRole("radio", { name: "Dark" }).check();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.goto("/coverage");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(page.getByRole("banner").getByRole("radio", { name: "Dark" })).toBeChecked();
  await audit(page);
});

test.describe("390 px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Coverage shows each company as a card, its filings with Indexed badges, and nothing scrolls sideways", async ({ page }) => {
    await page.goto("/coverage");
    await expect(page.locator("tbody tr")).toHaveCount(20);
    const table = page.getByRole("region", { name: "Companies and their indexed filings" });
    expect(await table.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
    await expect(page.locator("tbody tr").first().locator(".card-label")).toHaveText("CIK");
    await expect(page.locator("tbody .badge").first()).toHaveText("Indexed");
    await noSidewaysScroll(page);
    await audit(page);
  });

  test("on a phone every part shows at once, and the card fits, with the header's theme switch", async ({ page }) => {
    await allAtOnce(page);
    await expect(page.getByRole("banner").getByRole("group", { name: "Theme" })).toBeVisible();
    await noSidewaysScroll(page);
    await audit(page);
  });
});

// Recent questions on Ask: a sign-in's earlier answers come back without a model call, and stay its own.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { question, SESSION_COOKIE } from "./env.ts";
import { ask, audit, expect, newSignIn, noSidewaysScroll, test } from "./fixtures.ts";

const N01 = question("n01"); // numeric: one fact, one number check
const X04 = question("x04"); // textual: one passage
const TIME = /\d{1,2}:\d{2} [AP]M$/;

const pathOf = (url: string) => new URL(url).pathname;

/** The bodies the page posts to /api/answers from now on: a stored answer must post none. */
function answerPosts(page: Page): string[] {
  const posted: string[] = [];
  page.on("request", (request) => {
    if (pathOf(request.url()) === "/api/answers") posted.push(request.postData() ?? "");
  });
  return posted;
}

/** Ask, once its list of recent questions has loaded. */
async function openAsk(page: Page) {
  const listed = page.waitForResponse((response) => pathOf(response.url()) === "/api/recent");
  await page.goto("/ask");
  await listed;
}

/** Two answers, with their sources loaded: N01 is in the list while X04 is on screen. */
async function twoAnswered(page: Page) {
  await ask(page, N01);
  await expect(page.locator("#source-1 h4")).toContainText("AAPL");
  await ask(page, X04);
  await expect(page.locator("#source-1 h4")).toContainText("AMZN");
}

/** The focused element's accessible-ish name: its label, its text, or its id. */
const focused = (page: Page) =>
  page.evaluate(() => {
    const element = document.activeElement as HTMLElement;
    return element.getAttribute("aria-label") ?? (element.textContent?.trim() || element.id);
  });

const items = (page: Page) => page.getByTestId("recent").getByRole("button");

test("the list holds this sign-in's other questions with their times, leaving out the one on screen", async ({ page }) => {
  await twoAnswered(page);
  await expect(page.getByTestId("recent").getByRole("heading")).toHaveText("Recent questions");
  await expect(items(page)).toHaveCount(1);
  await expect(items(page)).toContainText(N01);
  await expect(items(page).locator("time")).toHaveText(TIME);
  await page.getByRole("button", { name: "New question" }).click(); // nothing on screen: both, newest first
  await expect(items(page)).toHaveCount(2);
  await expect(items(page).first()).toContainText(X04);
});

test("picking one shows its stored answer, reading, sources and number checks, and asks nothing", async ({ page }) => {
  await twoAnswered(page);
  const posted = answerPosts(page);
  await items(page).filter({ hasText: N01 }).click();
  await expect(page.getByTestId("answer")).toContainText("416,161,000,000 USD");
  await expect(page.getByTestId("stored")).toHaveText(/^From earlier in this session · \d{1,2}:\d{2} [AP]M$/);
  await expect(page.getByTestId("timings")).toHaveCount(0);
  await expect(page.getByTestId("read-as")).toBeVisible();
  await expect(page.getByTestId("checks").locator("tbody tr")).toHaveCount(1);
  await expect(page.locator("#source-1 h4")).toContainText("AAPL");
  await expect(page.getByLabel("Your question")).toHaveValue(N01);
  await expect(page.locator("#answer-text")).toBeFocused();
  await expect(page.getByTestId("ask-status")).toHaveText("Answer from earlier in this session, with 1 source.");
  await expect(items(page)).toHaveCount(1); // now X04, the one off screen
  await expect(items(page)).toContainText(X04);
  expect(posted).toEqual([]);
});

test("the same question again, in other letter case and spacing, comes back from earlier with Ask again", async ({ page }) => {
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible();
  await ask(page, `  ${N01.toLowerCase().replace("?", "")}  `);
  await expect(page.getByTestId("stored")).toHaveText(TIME);
  await expect(page.getByTestId("answer")).toContainText("416,161,000,000 USD");
  await expect(page.getByTestId("draft")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Ask again" })).toBeVisible();
  await expect(page.getByTestId("recent")).toHaveCount(0); // its one entry is the answer on screen
});

test("Ask again answers anew, with a draft and its timings, and the list keeps one entry", async ({ page }) => {
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible();
  await ask(page, N01);
  await expect(page.getByTestId("stored")).toBeVisible();
  const posted = answerPosts(page);
  await page.getByRole("button", { name: "Ask again" }).click();
  await expect(page.getByTestId("draft")).toBeVisible();
  await expect(page.getByTestId("timings")).toBeVisible();
  await expect(page.getByTestId("stored")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Ask again" })).toHaveCount(0);
  expect(posted.map((body) => JSON.parse(body))).toEqual([{ question: N01, fresh: true }]);
  await page.getByRole("button", { name: "New question" }).click();
  await expect(items(page)).toHaveCount(1);
});

test("while an answer is on its way, the list's questions wait", async ({ page }) => {
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible();
  await ask(page, `e2e: slow ${randomUUID()}`); // the mock drafts it for about 3 s
  await expect(page.getByTestId("draft")).toBeVisible();
  await expect(items(page)).toHaveAttribute("aria-disabled", "true");
  await items(page).click({ force: true }); // Playwright would wait for aria-disabled to go
  await expect(page.getByTestId("draft")).toBeVisible();
  await expect(page.getByTestId("stored")).toHaveCount(0);
});

test("refusals and failed answers are never listed", async ({ page }) => {
  await ask(page, question("o02"));
  await expect(page.getByTestId("answer")).toContainText("Not answered");
  for (const text of ["e2e: busy", "e2e: failed"]) {
    await ask(page, text);
    await expect(page.getByTestId("ask-error")).toBeVisible();
  }
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible();
  await page.getByRole("button", { name: "New question" }).click();
  await expect(items(page)).toHaveCount(1);
  await expect(items(page)).toContainText(N01);
});

test("another sign-in sees none of these questions, and asking one answers anew", async ({ page, context }) => {
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible();
  await newSignIn(context);
  await openAsk(page);
  await expect(page.getByTestId("recent")).toHaveCount(0);
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible(); // a new answer, not the other sign-in's
  await expect(page.getByTestId("stored")).toHaveCount(0);
});

test("signing out has the API forget the list, so the old cookie brought back finds none", async ({ page, context }) => {
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible();
  const old = (await context.cookies()).find((cookie) => cookie.name === SESSION_COOKIE)!;
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL("/login");
  await context.addCookies([old]); // a saved copy still signs in: sessions are stateless
  await openAsk(page);
  await expect(page.getByTestId("recent")).toHaveCount(0);
  await ask(page, N01);
  await expect(page.getByTestId("timings")).toBeVisible();
});

test("from a stored answer, Tab goes through Copy, Ask again and New question to the list", async ({ page }) => {
  await twoAnswered(page);
  await items(page).filter({ hasText: N01 }).click();
  await expect(page.locator("#answer-text")).toBeFocused();
  await expect(page.locator("#source-1 h4")).toContainText("AAPL");
  const order: string[] = [];
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    order.push(await focused(page));
  }
  const copy = order.indexOf("Copy answer with sources");
  expect(copy).toBeGreaterThan(0); // the answer's citation first
  expect(order.slice(copy, copy + 4)).toEqual([
    "Copy answer with sources",
    "Ask again",
    "New question",
    expect.stringContaining(X04),
  ]);
});

for (const colorScheme of ["light", "dark"] as const) {
  test(`axe passes with the list beside a new answer and a stored one, ${colorScheme}`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await twoAnswered(page);
    await audit(page);
    await items(page).click();
    await expect(page.getByTestId("stored")).toBeVisible();
    await expect(page.locator("#source-1 h4")).toContainText("AAPL");
    await audit(page);
  });
}

test.describe("390 px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the list fits a phone, each question a full-width target at least 44 px tall", async ({ page }) => {
    await twoAnswered(page);
    await page.getByRole("button", { name: "New question" }).click();
    await expect(items(page)).toHaveCount(2);
    for (const item of await items(page).all()) {
      const box = await item.boundingBox();
      expect(box?.height).toBeGreaterThanOrEqual(44);
      expect(box?.width).toBeGreaterThan(300);
    }
    await noSidewaysScroll(page);
  });
});

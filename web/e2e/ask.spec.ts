import { randomUUID } from "node:crypto";

import type { Route } from "@playwright/test";

import { API_KEY, MOCK, question, snapshot } from "./env.ts";
import { ask, audit, expect, test } from "./fixtures.ts";

/** A recorded answer's text and its first citation. */
function recorded(id: string) {
  const { answer, citations } = snapshot.answers.find((item) => item.id === id)!.answer;
  return { answer, cited: citations[0] as { quote: string; filing_url: string } };
}

test("numeric: the draft streams, then the checked answer links its fact card", async ({ page }) => {
  await ask(page, question("n01"));
  await expect(page.getByTestId("draft")).toContainText("citations not checked yet");
  const answer = page.getByTestId("answer");
  await expect(answer).toContainText("416,161,000,000 USD");
  await expect(page.getByTestId("draft")).toHaveCount(0);
  await expect(page.getByTestId("ask-status")).toHaveText("Answer ready, with 1 source.");
  await answer.getByRole("link", { name: /^Source 1: AAPL fact, Revenue/ }).click();
  await expect(page).toHaveURL(/#source-1$/);
  await expect(page.locator("#source-1")).toContainText("416,161,000,000 USD");
});

test("textual: a chunk card names its filing and item, and marks the quote", async ({ page }) => {
  await ask(page, question("x04"));
  const card = page.locator("#source-1");
  await expect(card.getByRole("heading")).toHaveText("Source 1: AMZN 10-K FY2025, Item 1");
  await expect(card.locator("mark")).toContainText("three segments");
});

test("the source panel fits the window from the first screen, and a citation brings its quote into view in it", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 360 }); // the narrowest two columns; short, so the quote starts below the card's first screen
  await ask(page, question("x02"));
  await expect(page.locator("#source-1").getByRole("heading")).toContainText("NVDA");
  const gapBelowPanel = () => page.evaluate(() => innerHeight - document.querySelector("section.sources")!.getBoundingClientRect().bottom);
  expect(await gapBelowPanel()).toBeCloseTo(16, 0); // its bottom edge on screen at once, 1rem above the window's
  await page.getByTestId("answer").getByRole("link", { name: /^Source 1:/ }).first().click();
  const shown = () =>
    page.evaluate(() => {
      const panel = document.querySelector("section.sources")!.getBoundingClientRect();
      const quote = document.querySelector("#source-1 mark")!.getBoundingClientRect();
      return {
        panelOnScreen: panel.top >= 0 && panel.bottom <= innerHeight,
        quoteInPanel: quote.top >= panel.top && quote.bottom <= panel.bottom,
      };
    });
  await expect.poll(shown).toEqual({ panelOnScreen: true, quoteInPanel: true });
});

test("comparison: one fact card per company", async ({ page }) => {
  await ask(page, question("c02"));
  await expect(page.locator("#source-1").getByRole("heading")).toContainText("GOOGL fact");
  await expect(page.locator("#source-2").getByRole("heading")).toContainText("META fact");
});

test("a refusal says it is not answered, with its reason and no sources", async ({ page }) => {
  await ask(page, question("o02"));
  const answer = page.getByTestId("answer");
  await expect(answer).toContainText("Not answered");
  await expect(answer).toContainText("SEC filings cannot answer this question");
  await expect(page.getByRole("heading", { name: "Sources" })).toHaveCount(0);
});

test("the answer's header says when its first words came, when it was complete, and how many sources it has", async ({ page }) => {
  await ask(page, question("c12"));
  await expect(page.getByTestId("timings")).toHaveText(/^First words in \d+\.\d s · complete in \d+\.\d s · 4 sources$/);
});

test("Copy answer with sources puts the answer on the clipboard, then each source's name, quote and link", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await ask(page, question("x04"));
  await expect(page.locator("#source-1").getByRole("heading")).toContainText("AMZN");
  await page.getByRole("button", { name: "Copy answer with sources" }).click();
  await expect(page.getByTestId("ask-status")).toHaveText("Copied the answer with its sources.");
  const { answer, cited } = recorded("x04");
  const copied = (await page.evaluate(() => navigator.clipboard.readText())).replaceAll("\r\n", "\n"); // CRLF on Windows
  expect(copied).toBe(`${answer}\n\nSources\n[1] AMZN 10-K FY2025, Item 1: "${cited.quote}" ${cited.filing_url}`);
});

test("a refusal offers New question, and nothing to copy", async ({ page }) => {
  await ask(page, question("o02"));
  await expect(page.getByTestId("answer")).toContainText("Not answered");
  await expect(page.getByRole("button", { name: "New question" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Copy answer with sources" })).toHaveCount(0);
});

test("New question clears the answer and the question box, and puts the focus there", async ({ page }) => {
  await ask(page, question("n01"));
  await expect(page.locator("#source-1").getByRole("heading")).toContainText("AAPL");
  await page.getByRole("button", { name: "New question" }).click();
  const box = page.getByLabel("Your question");
  await expect(box).toBeFocused();
  await expect(box).toHaveValue("");
  await expect(page.getByTestId("answer")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Sources" })).toHaveCount(0);
  await expect(page.getByTestId("ask-status")).toHaveText("");
});

test("New question while the sources still load stops their lookup, and the next question runs", async ({ page }) => {
  await page.route("**/api/sources", () => {}); // never answers
  await ask(page, question("n01"));
  await expect(page.getByTestId("answer")).toContainText("416,161,000,000 USD");
  await page.getByRole("button", { name: "New question" }).click();
  await page.getByLabel("Your question").fill(question("x04"));
  await page.getByRole("button", { name: "Ask" }).click();
  await expect(page.getByTestId("answer")).toContainText("three reportable segments");
});

test("an answer validation rewrote shows its warnings", async ({ page }) => {
  await ask(page, "e2e: rewritten");
  await expect(page.getByTestId("warnings")).toContainText("written again");
});

const ERRORS: [string, string, boolean][] = [
  ["e2e: rate limited", "Too many questions. Try again in 7 s.", false],
  ["e2e: switched off", "Live answers are switched off on this server.", true],
  ["e2e: busy", "The service is busy. Try again in 2 s.", false],
  ["e2e: failed", "No answer within 30 s.", false],
];

for (const [text, message, demoLink] of ERRORS) {
  test(`error state: ${text}`, async ({ page }) => {
    await ask(page, text);
    const error = page.getByTestId("ask-error");
    await expect(error).toContainText(message);
    await expect(error.getByRole("link", { name: "See the saved answers" })).toHaveCount(demoLink ? 1 : 0);
    await expect(page.getByTestId("draft")).toHaveCount(0);
    await expect(page.getByTestId("ask-status")).toHaveText(message);
  });
}

test("a network error on the stream itself says the web server could not be reached", async ({ page }) => {
  await page.route("**/api/answers", (route) => route.abort());
  await ask(page, question("n01"));
  const error = page.getByTestId("ask-error");
  await expect(error).toContainText("The web server could not be reached.");
  await expect(error.getByRole("link", { name: "See the saved answers" })).toHaveCount(1);
  await expect(page.getByTestId("ask-status")).toHaveText("The web server could not be reached.");
});

const SOURCES_FAILURES: [string, (route: Route) => Promise<void>][] = [
  ["an error reply", (route) => route.fulfill({ status: 503, json: { code: "offline", detail: "The API is offline." } })],
  ["a network error", (route) => route.abort()],
];

for (const [name, failure] of SOURCES_FAILURES) {
  test(`sources: ${name} keeps the answer and says its sources could not be loaded`, async ({ page }) => {
    await page.route("**/api/sources", failure);
    await ask(page, question("n01"));
    await expect(page.getByTestId("sources-error")).toHaveText("Sources could not be loaded.");
    await expect(page.getByTestId("ask-status")).toHaveText("Answer ready, with 1 source. Sources could not be loaded.");
    await expect(page.getByTestId("ask-error")).toHaveCount(0);
    await expect(page.locator("#source-1").getByRole("heading")).toHaveText("Source 1");
    await audit(page);
  });
}

test("leaving Ask through a header link stops its answer stream at the API", async ({ page, request }) => {
  const slow = `e2e: slow ${randomUUID()}`; // the mock streams it for about 3 s
  await ask(page, slow);
  await expect(page.getByTestId("draft")).toBeVisible();
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Coverage" }).click();
  await expect(page).toHaveURL(/\/coverage$/);
  // Chromium reports even a finished stream as net::ERR_ABORTED, so the mock says whether it was cut.
  const cut = async () => {
    const reply = await request.get(`${MOCK}/e2e/cut?question=${encodeURIComponent(slow)}`, { headers: { "X-API-Key": API_KEY } });
    return ((await reply.json()) as { cut: boolean }).cut;
  };
  await expect.poll(cut).toBe(true);
});

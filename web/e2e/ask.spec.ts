import { question } from "./env.ts";
import { ask, expect, test } from "./fixtures.ts";

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
  await expect(answer.getByRole("heading", { name: "Sources" })).toHaveCount(0);
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

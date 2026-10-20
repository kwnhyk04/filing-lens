// What axe cannot see: the focus order and keyboard-only use.
import type { Page } from "@playwright/test";

import { PASSWORD, question } from "./env.ts";
import { expect, signedOut, test } from "./fixtures.ts";

/** The focused element's accessible-ish name: its label, its text, or its id. */
const focused = (page: Page) =>
  page.evaluate(() => {
    const element = document.activeElement as HTMLElement;
    return element.getAttribute("aria-label") ?? (element.textContent?.trim() || element.id);
  });

async function tab(page: Page, times = 1) {
  for (let i = 0; i < times; i++) await page.keyboard.press("Tab");
}

test("the skip link comes first, then the header, then the question form", async ({ page }) => {
  await page.goto("/");
  const order: string[] = [];
  for (let i = 0; i < 7; i++) {
    await tab(page);
    order.push(await focused(page));
  }
  expect(order).toEqual(["Skip to content", "FilingLens", "Ask", "Coverage", "Sign out", "question", "Ask"]);
  await page.goto("/");
  await tab(page);
  await page.keyboard.press("Enter");
  await tab(page);
  expect(await focused(page)).toBe("question");
});

test("ask, jump to a citation and back, then sign out, by keyboard alone", async ({ page }) => {
  await page.goto("/");
  await tab(page, 6);
  await page.keyboard.type(question("x04"));
  await tab(page);
  await page.keyboard.press("Enter");
  await expect(page.locator("#source-1").getByRole("heading")).toContainText("AMZN");
  await tab(page);
  expect(await focused(page)).toBe("Source 1: AMZN 10-K FY2025, Item 1");
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.activeElement?.id)).toBe("source-1");
  await tab(page, 2);
  expect(await focused(page)).toContain("Back to the answer");
  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => document.activeElement?.id)).toBe("answer-text");
  await page.goto("/");
  await tab(page, 5);
  expect(await focused(page)).toBe("Sign out");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/login");
});

test("after an answer, Tab goes from its citations to Copy and New question, which returns to the question box", async ({ page }) => {
  await page.goto("/");
  await tab(page, 6);
  await page.keyboard.type(question("x04"));
  await tab(page);
  await page.keyboard.press("Enter");
  await expect(page.locator("#source-1").getByRole("heading")).toContainText("AMZN");
  const order: string[] = [];
  for (let i = 0; i < 4; i++) {
    await tab(page);
    order.push(await focused(page));
  }
  const cite = "Source 1: AMZN 10-K FY2025, Item 1"; // x04 cites its source twice
  expect(order).toEqual([cite, cite, "Copy answer with sources", "New question"]);
  await page.keyboard.press("Enter");
  await expect(page.getByLabel("Your question")).toBeFocused();
});

test.describe("signed out", () => {
  test.use(signedOut);

  test("sign in by keyboard alone", async ({ page }) => {
    await page.goto("/login");
    await tab(page, 2);
    expect(await focused(page)).toBe("password");
    await page.keyboard.type(PASSWORD);
    await page.keyboard.press("Enter");
    await expect(page.getByRole("heading", { level: 1, name: "Ask" })).toBeVisible();
  });
});

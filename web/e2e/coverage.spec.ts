// Coverage: the companies in Origin UI's table with numeric pagination, ported into the app's CSS (docs/design.md).
// The page and the size live in the URL; the size is remembered for the next visit.
import type { Page } from "@playwright/test";

import { snapshot } from "./env.ts";
import { audit, expect, noSidewaysScroll, test } from "./fixtures.ts";

const rows = (page: Page) => page.locator("tbody tr");
const pager = (page: Page) => page.getByRole("navigation", { name: "Pages" });
const previous = (page: Page) => pager(page).getByRole("button", { name: "Go to previous page" });
const next = (page: Page) => pager(page).getByRole("button", { name: "Go to next page" });
const number = (page: Page, n: number) => pager(page).getByRole("button", { name: `Page ${n}`, exact: true });
const size = (page: Page) => page.getByLabel("Results per page");
/** The company name a row starts with. */
const company = (n: number) => snapshot.companies[n - 1].name;

test("10 companies a page, with the pager: Page 1 of 3, Previous, the page numbers, Next, and the size", async ({ page }) => {
  await page.goto("/coverage");
  await expect(rows(page)).toHaveCount(10);
  await expect(rows(page).first()).toContainText(company(1));
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
  await expect(previous(page)).toBeDisabled();
  await expect(number(page, 1)).toHaveAttribute("aria-current", "page");
  for (const n of [2, 3]) await expect(number(page, n)).not.toHaveAttribute("aria-current", "page");
  await expect(next(page)).toBeEnabled();
  await expect(size(page)).toHaveValue("10");
  await expect(size(page).locator("option")).toHaveText(["10 / page", "20 / page", "50 / page"]);
  await expect(page.getByRole("columnheader")).toHaveText(["Company", "CIK", "Filings"]);
  await expect(page.getByRole("link", { name: "10-K FY2025" }).first()).toHaveAttribute("href", /^https:\/\/www\.sec\.gov\//);
  await audit(page);
});

test("the page lives in the URL: Next and a page number move it, and Back, a refresh and a shared link keep it", async ({ page }) => {
  await page.goto("/coverage");
  await next(page).click();
  await expect(page).toHaveURL("/coverage?page=2&size=10");
  await expect(rows(page).first()).toContainText(company(11));
  await expect(page.getByText("Page 2 of 3", { exact: true })).toBeVisible();
  await number(page, 3).click();
  await expect(page).toHaveURL("/coverage?page=3&size=10");
  await expect(next(page)).toBeDisabled();
  await expect(rows(page).first()).toContainText(company(21));
  await page.goBack();
  await expect(page).toHaveURL("/coverage?page=2&size=10");
  await expect(rows(page).first()).toContainText(company(11));
  await page.reload();
  await expect(rows(page).first()).toContainText(company(11));
  await expect(number(page, 2)).toHaveAttribute("aria-current", "page");
  await page.goto("/coverage?page=3&size=10");
  await expect(page.getByText("Page 3 of 3", { exact: true })).toBeVisible();
});

test("a new size keeps the first row on screen, on the page that holds it, and is remembered for the next visit", async ({ page }) => {
  await page.goto("/coverage?page=2&size=10");
  const first = rows(page).filter({ hasText: company(11) });
  await expect(first).toBeVisible();
  await size(page).selectOption("20");
  await expect(page).toHaveURL("/coverage?page=1&size=20");
  await expect(rows(page)).toHaveCount(20);
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await expect(first).toBeInViewport();
  await page.goto("/coverage");
  await expect(size(page)).toHaveValue("20");
  await expect(rows(page)).toHaveCount(20);
  await size(page).selectOption("50");
  await expect(rows(page)).toHaveCount(30);
  await expect(page.getByText("Page 1 of 1", { exact: true })).toBeVisible();
  await expect(previous(page)).toBeDisabled();
  await expect(next(page)).toBeDisabled();
});

test("where storage is blocked the pager still works, and the size is not remembered", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new DOMException("The storage is blocked.", "SecurityError");
      },
    });
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/coverage");
  await size(page).selectOption("20");
  await expect(rows(page)).toHaveCount(20);
  await page.goto("/coverage");
  await expect(rows(page)).toHaveCount(10);
  expect(errors).toEqual([]);
});

test("a page past the end shows the last, and a page or size that is not offered falls back", async ({ page }) => {
  await page.goto("/coverage?page=9&size=10");
  await expect(page.getByText("Page 3 of 3", { exact: true })).toBeVisible();
  await page.goto("/coverage?size=7");
  await expect(rows(page)).toHaveCount(10);
  await page.goto("/coverage?page=x");
  await expect(page.getByText("Page 1 of 3", { exact: true })).toBeVisible();
});

test("each listed filing carries an Indexed badge, since the API lists indexed filings only", async ({ page }) => {
  await page.goto("/coverage");
  const filings = page.locator("tbody li").filter({ has: page.getByRole("link") });
  await expect(filings).toHaveCount(10);
  await expect(filings.locator(".badge.ok")).toHaveText(Array(10).fill("Indexed"));
});

test("while the API answers, a skeleton in the table's shape holds the place under the header", async ({ page }) => {
  await page.goto("/coverage?after=e2e-slow", { waitUntil: "commit" }); // the mock answers after 3 s
  const skeleton = page.getByTestId("coverage-skeleton");
  await expect(skeleton).toBeVisible();
  await expect(skeleton).toHaveAttribute("aria-busy", "true");
  await expect(page.getByRole("banner").getByRole("link", { name: "Coverage" })).toBeVisible();
  await expect(rows(page)).toHaveCount(10);
  await expect(skeleton).toHaveCount(0);
});

test("a cursor the API does not know goes to the first page", async ({ page }) => {
  await page.goto("/coverage?after=bogus");
  await expect(page).toHaveURL("/coverage");
  await expect(rows(page)).toHaveCount(10);
});

test("an unknown address renders inside the shell, not a bare 404", async ({ page }) => {
  const response = await page.goto("/no-such-page");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "see the demo" })).toBeVisible();
});

test.describe("390 px", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the pager shows Page 2 of 3 with Previous, Next and the size; each company reads as a card", async ({ page }) => {
    await page.goto("/coverage?page=2&size=10");
    await expect(page.getByText("Page 2 of 3", { exact: true })).toBeVisible();
    await expect(previous(page)).toBeVisible();
    await expect(next(page)).toBeVisible();
    await expect(size(page)).toBeVisible();
    for (const n of [1, 2, 3]) await expect(number(page, n)).toBeHidden();
    await expect(rows(page).first().locator(".card-label")).toHaveText("CIK");
    await noSidewaysScroll(page);
    await audit(page);
  });
});

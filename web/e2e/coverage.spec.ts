import { expect, test } from "./fixtures.ts";

test("coverage pages by cursor, 20 companies at a time", async ({ page }) => {
  await page.goto("/coverage");
  const rows = page.locator("tbody tr");
  await expect(rows).toHaveCount(20);
  await page.getByRole("link", { name: "Next page" }).click();
  await expect(rows).toHaveCount(10);
  await expect(page.getByRole("link", { name: "Next page" })).toHaveCount(0);
  await page.getByRole("link", { name: "First page" }).click();
  await expect(rows).toHaveCount(20);
  await expect(page.getByRole("link", { name: "10-K FY2025" }).first()).toHaveAttribute("href", /^https:\/\/www\.sec\.gov\//);
});

test("each listed filing carries an Indexed pill, since the API lists indexed filings only", async ({ page }) => {
  await page.goto("/coverage");
  const filings = page.locator("tbody li").filter({ has: page.getByRole("link") });
  await expect(filings).toHaveCount(20);
  await expect(filings.locator(".pill")).toHaveText(Array(20).fill("Indexed"));
});

test("a cursor the API does not know goes to the first page", async ({ page }) => {
  await page.goto("/coverage?after=bogus");
  await expect(page).toHaveURL("/coverage");
  await expect(page.locator("tbody tr")).toHaveCount(20);
});

test("an unknown address renders inside the shell, not a bare 404", async ({ page }) => {
  const response = await page.goto("/no-such-page");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { level: 1, name: "Page not found" })).toBeVisible();
  await expect(page.getByRole("link", { name: "see the demo" })).toBeVisible();
});

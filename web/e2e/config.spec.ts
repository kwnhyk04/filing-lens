// A rejected API key and an unexpected API problem: each renders inside the shell, never the demo.
import { ask, audit, expect, noSidewaysScroll, test } from "./fixtures.ts";

const REQUEST_ID = /[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}/;

test("a rejected key shows the configuration error with its request id, never the demo", async ({ page }) => {
  await page.goto("/coverage?after=e2e-rejected");
  await expect(page).toHaveURL("/coverage?after=e2e-rejected");
  await expect(page.getByTestId("config-error")).toContainText(REQUEST_ID);
  await audit(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await noSidewaysScroll(page);
});

test("Ask names a rejected key with its request id, and offers no demo", async ({ page }) => {
  await ask(page, "e2e: rejected");
  const error = page.getByTestId("ask-error");
  await expect(error).toContainText("The API refused this web server's key.");
  await expect(error).toContainText(REQUEST_ID);
  await expect(error.getByRole("link")).toHaveCount(0);
});

test("an unexpected API problem renders the error page inside the shell", async ({ page }) => {
  await page.goto("/coverage?after=e2e-error");
  await expect(page.getByRole("heading", { level: 1, name: "Something went wrong" })).toBeVisible();
  await expect(page.getByRole("link", { name: "see the demo" })).toBeVisible();
  await audit(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await noSidewaysScroll(page);
});

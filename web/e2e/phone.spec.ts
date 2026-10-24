// A 390 px phone: no page scrolls sideways (wide tables scroll inside their own region).
import { ask, expect, noSidewaysScroll, signedOut, test } from "./fixtures.ts";

test.use({ viewport: { width: 390, height: 844 } });

for (const path of ["/", "/ask", "/coverage", "/demo", "/demo/coverage", "/no-such-page"]) {
  test(`390 px: ${path}`, async ({ page }) => {
    await page.goto(path);
    await noSidewaysScroll(page);
  });
}

test("390 px: an answer with its sources", async ({ page }) => {
  await ask(page, "e2e: rewritten");
  await expect(page.locator("#source-2").getByRole("heading")).toContainText("NVDA");
  await noSidewaysScroll(page);
});

test.describe("signed out", () => {
  test.use(signedOut);

  test("390 px: /login", async ({ page }) => {
    await page.goto("/login");
    await noSidewaysScroll(page);
  });
});

// axe on every page, live and demo: any WCAG 2.2 A or AA violation fails.
import { ask, audit, expect, signedOut, signIn, test } from "./fixtures.ts";

for (const path of ["/", "/coverage", "/demo", "/demo/coverage", "/no-such-page"]) {
  test(`axe: ${path}`, async ({ page }) => {
    await page.goto(path);
    await audit(page);
  });
}

test("axe: an answer with its sources and warnings", async ({ page }) => {
  await ask(page, "e2e: rewritten");
  await expect(page.locator("#source-1").getByRole("heading")).toContainText("NVDA");
  await audit(page);
});

test("axe: an error state", async ({ page }) => {
  await ask(page, "e2e: switched off");
  await expect(page.getByTestId("ask-error")).toBeVisible();
  await audit(page);
});

test.describe("dark theme", () => {
  test.use({ colorScheme: "dark" });

  for (const path of ["/coverage", "/demo"]) {
    test(`axe, dark: ${path}`, async ({ page }) => {
      await page.goto(path);
      await audit(page);
    });
  }

  test("axe, dark: an error state", async ({ page }) => {
    await ask(page, "e2e: busy");
    await expect(page.getByTestId("ask-error")).toBeVisible();
    await audit(page);
  });
});

test.describe("signed out", () => {
  test.use(signedOut);

  test("axe: sign-in, and its error", async ({ page }) => {
    await page.goto("/login");
    await audit(page);
    await signIn(page, "not the password");
    await expect(page.getByTestId("sign-in-error")).toHaveText("Wrong password.");
    await audit(page);
  });
});

// Runs last (its own project), in order: the last test leaves the live server's sign-in locked
// for 15 minutes.
import type { Page } from "@playwright/test";

import { expect, signedOut, signIn, test } from "./fixtures.ts";

test.use(signedOut);
test.describe.configure({ mode: "serial" });

const posted = (page: Page) =>
  page.waitForResponse((reply) => reply.request().method() === "POST" && new URL(reply.url()).pathname === "/login");

async function attempt(page: Page, password?: string) {
  await Promise.all([posted(page), signIn(page, password)]);
}

/** A wrong password sent from the focused button by keyboard. */
async function attemptByKeyboard(page: Page, password: string) {
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).focus();
  await Promise.all([posted(page), page.keyboard.press("Enter")]);
  await expect(page.getByTestId("sign-in-error")).toHaveText("Wrong password.");
}

test("a keyboard sign-in keeps focus on the button, and a repeated error is a new message", async ({ page }) => {
  await page.goto("/login");
  await attemptByKeyboard(page, "wrong password a");
  expect(await page.evaluate(() => document.activeElement?.textContent?.trim())).toBe("Sign in");
  const first = await page.getByTestId("sign-in-error").locator("span").elementHandle();
  await attemptByKeyboard(page, "wrong password b");
  expect(await first?.evaluate((node) => node.isConnected), "screen readers hear the repeat").toBe(false);
});

test("five wrong passwords lock sign-in, even for the right one", async ({ page, context }) => {
  await page.goto("/login");
  await signIn(page); // a success clears earlier attempts
  await expect(page.getByRole("heading", { level: 1, name: "Ask" })).toBeVisible();
  await context.clearCookies();
  await page.goto("/login");
  for (let i = 1; i <= 5; i++) {
    await attempt(page, `wrong password ${i}`);
    await expect(page.getByTestId("sign-in-error")).toHaveText("Wrong password.");
  }
  await attempt(page);
  await expect(page.getByTestId("sign-in-error")).toContainText("Too many failed attempts");
});

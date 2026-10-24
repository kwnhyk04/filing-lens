// The suite's `test`: any CSP violation on a page fails the test that opened it.
import AxeBuilder from "@axe-core/playwright";
import { test as base, expect, type Page } from "@playwright/test";

import { PASSWORD } from "./env.ts";

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];

/** axe on the page as it stands: any WCAG 2.2 A or AA violation fails. */
export async function audit(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((node) => node.target.join(" ")).join(", ")}`)).toEqual([]);
}

/** The page fits a 390 px phone without scrolling sideways. */
export async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
}

export const test = base.extend<{ cspGuard: void }>({
  cspGuard: [
    async ({ page }, use) => {
      const violations: string[] = [];
      await page.exposeFunction("reportCspViolation", (text: string) => violations.push(text));
      await page.addInitScript(() => {
        document.addEventListener("securitypolicyviolation", (event) => {
          const report = (window as unknown as { reportCspViolation(text: string): void }).reportCspViolation;
          report(`${event.violatedDirective} ${event.blockedURI}`);
        });
      });
      await use();
      expect(violations, "CSP violations").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };

/** For signed-out specs: no cookies at all, whatever the project stores. */
export const signedOut = { storageState: { cookies: [], origins: [] } };

export async function signIn(page: Page, password = PASSWORD) {
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export async function ask(page: Page, question: string) {
  await page.goto("/ask");
  await page.getByLabel("Your question").fill(question);
  await page.getByRole("button", { name: "Ask" }).click();
}

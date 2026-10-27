// Every screen in light, dark and phone width, for comparing designs side by side. Each passes axe
// first, then goes to docs/screenshots/ui/<screen>-<variant>.png, or into SCREENS_DIR when that is set.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { OFFLINE, question } from "./env.ts";
import { ask, audit, expect, signIn, test } from "./fixtures.ts";

const DIR = process.env.SCREENS_DIR ?? "../docs/screenshots/ui";
const TOP_ONLY = new Set(["offline"]); // below its banner it is the demo page, shot in full as "demo"

const VARIANTS = [
  { name: "light", viewport: { width: 1280, height: 800 }, colorScheme: "light" },
  { name: "dark", viewport: { width: 1280, height: 800 }, colorScheme: "dark" },
  { name: "phone", viewport: { width: 390, height: 844 }, colorScheme: "light" },
] as const;

/** An answer whose card `n` has loaded its source, which names `ticker`. */
async function answered(page: Page, text: string, n: number, ticker: string) {
  await ask(page, text);
  await expect(page.locator(`#source-${n} h4`)).toContainText(ticker);
}

async function signedOut(page: Page, path: string) {
  await page.context().clearCookies();
  await page.goto(path);
}

/** Each screen: how to reach it, settled. */
const SCREENS: Record<string, (page: Page) => Promise<unknown>> = {
  "sign-in": (page) => signedOut(page, "/login"),
  "sign-in-error": async (page) => {
    await signedOut(page, "/login");
    await signIn(page, "not the password");
    await expect(page.getByTestId("sign-in-error")).toHaveText("Wrong password.");
  },
  landing: (page) => signedOut(page, "/"),
  ask: (page) => page.goto("/ask"),
  "ask-draft": async (page) => {
    await ask(page, `e2e: slow ${randomUUID()}`);
    await expect(page.getByTestId("draft")).toContainText("Still drafting.");
  },
  "ask-numeric": (page) => answered(page, question("n01"), 1, "AAPL"),
  "ask-textual": (page) => answered(page, question("x04"), 1, "AMZN"),
  "ask-comparison": (page) => answered(page, question("c12"), 4, "TSLA"),
  "ask-calculation": async (page) => {
    await answered(page, "e2e: calculated", 1, "GOOGL");
    await page.getByRole("link", { name: /^Source 3: Calculated/ }).click(); // the [3] marker opens its card
    await expect(page.locator("#source-3")).toBeInViewport();
  },
  "ask-warnings": (page) => answered(page, "e2e: rewritten", 2, "NVDA"),
  "ask-refusal": async (page) => {
    await ask(page, question("o02"));
    await expect(page.getByTestId("answer")).toContainText("Not answered");
  },
  "ask-error": async (page) => {
    await ask(page, "e2e: switched off");
    await expect(page.getByTestId("ask-error")).toBeVisible();
  },
  "ask-sources-failed": async (page) => {
    await page.route("**/api/sources", (route) => route.abort());
    await ask(page, question("n01"));
    await expect(page.getByTestId("sources-error")).toBeVisible();
  },
  coverage: async (page) => {
    await page.goto("/coverage");
    await expect(page.locator("tbody tr")).toHaveCount(20);
  },
  demo: (page) => signedOut(page, "/demo"),
  "demo-coverage": (page) => signedOut(page, "/demo/coverage"),
  offline: async (page) => {
    await page.goto(`${OFFLINE}/ask`);
    await expect(page.getByTestId("demo-banner")).toContainText("The live service is offline");
  },
  "not-found": (page) => page.goto("/no-such-page"),
  error: async (page) => {
    await page.goto("/coverage?after=e2e-error");
    await expect(page.getByRole("heading", { level: 1, name: "Something went wrong" })).toBeVisible();
  },
  "config-error": async (page) => {
    await page.goto("/coverage?after=e2e-rejected");
    await expect(page.getByTestId("config-error")).toBeVisible();
  },
};

for (const variant of VARIANTS) {
  test.describe(variant.name, () => {
    test.use({ viewport: variant.viewport, colorScheme: variant.colorScheme });
    for (const [screen, open] of Object.entries(SCREENS)) {
      test(screen, async ({ page }) => {
        await open(page);
        await audit(page);
        const path = `${DIR}/${screen}-${variant.name}.png`;
        await page.screenshot({ path, fullPage: !TOP_ONLY.has(screen), animations: "disabled" });
      });
    }
  });
}

// Every screen in light, dark and phone width, for comparing designs side by side. Each passes axe
// first, then goes to docs/screenshots/ui/<screen>-<variant>.png, or into SCREENS_DIR when that is set.
// SCREENS_WIDTHS (such as "1280,1440,1920,390") shoots each width in light and dark instead, as
// <screen>-<width>-<theme>.png. SCREENS_MOTION=1 shoots its desktop widths with motion allowed, so on a
// graphics card (E2E_CHANNEL=msedge) Ask's moving stage plays: each Ask screen then waits for it.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { OFFLINE, question } from "./env.ts";
import { audit, expect, signIn, test } from "./fixtures.ts";

const DIR = process.env.SCREENS_DIR ?? "../docs/screenshots/ui";
const TOP_ONLY = new Set(["offline"]); // below its banner it is the demo page, shot in full as "demo"

// Reduced motion: the landing's hero stays the still, so its shots come out the same every run.
const WIDTHS = process.env.SCREENS_WIDTHS?.split(",").map(Number);
const MOTION = process.env.SCREENS_MOTION === "1";
const VARIANTS = WIDTHS
  ? WIDTHS.flatMap((width) =>
      (["light", "dark"] as const).map((colorScheme) => ({
        name: `${width}-${colorScheme}`,
        viewport: { width, height: width < 640 ? 844 : 900 },
        colorScheme,
        reducedMotion: MOTION && width >= 1024 ? ("no-preference" as const) : ("reduce" as const),
      })),
    )
  : ([
      { name: "light", viewport: { width: 1280, height: 800 }, colorScheme: "light", reducedMotion: "reduce" },
      { name: "dark", viewport: { width: 1280, height: 800 }, colorScheme: "dark", reducedMotion: "reduce" },
      { name: "phone", viewport: { width: 390, height: 844 }, colorScheme: "light", reducedMotion: "reduce" },
    ] as const);

/** Ask, its moving stage ready first when it plays (it loads after the page), then the question sent. */
async function ask(page: Page, text: string) {
  await openAsk(page);
  await page.getByLabel("Your question").fill(text);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
}

async function openAsk(page: Page) {
  await page.goto("/ask");
  if (await moving(page)) await expect(page.locator(".stage")).toHaveAttribute("data-live", "on", { timeout: 15_000 });
}

/** Whether this shot plays the moving stage: hero-motion.tsx's desktop with motion allowed, which on a graphics
    card loads it (a software renderer keeps the calm stage, and the wait for it fails). */
const moving = (page: Page) =>
  page.evaluate(
    () => matchMedia("(min-width: 64rem) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)").matches,
  );

/** The moving stage at rest once its pulls have played, and its field faded in; the calm stage at once. */
async function rested(page: Page) {
  if (!(await moving(page))) return;
  await expect(page.locator(".stage-field canvas")).toHaveCount(1, { timeout: 15_000 });
  await expect(page.locator(".stage .pb-stage")).toHaveAttribute("data-moving", "false", { timeout: 30_000 });
}

/** An answer whose card `n` has loaded its source, which names `ticker`. */
async function answered(page: Page, text: string, n: number, ticker: string) {
  await ask(page, text);
  await expect(page.locator(`#source-${n} h4`)).toContainText(ticker);
  await rested(page);
}

async function signedOut(page: Page, path: string) {
  await page.context().clearCookies();
  await page.goto(path);
}

/** Each screen: how to reach it, settled. */
const SCREENS: Record<string, (page: Page) => Promise<unknown>> = {
  "sign-in": (page) => signedOut(page, "/login"),
  "sign-in-error": async (page) => {
    // Locally every sign-in shares one limiter bucket, which a success empties: signing in first keeps the
    // many widths' wrong tries under the lockout's five.
    await signedOut(page, "/login");
    await signIn(page);
    await expect(page).toHaveURL("/ask");
    await signedOut(page, "/login");
    await signIn(page, "not the password");
    await expect(page.getByTestId("sign-in-error")).toHaveText("Wrong password.");
  },
  landing: (page) => signedOut(page, "/"),
  "landing-signed-out": async (page) => {
    await signedOut(page, "/?signed-out=1");
    await expect(page.getByRole("status").filter({ hasText: "You're signed out." })).toBeVisible();
  },
  ask: async (page) => {
    await openAsk(page);
    await rested(page);
  },
  "ask-reading": async (page) => {
    await ask(page, `e2e: slow ${randomUUID()}`);
    await expect(page.getByTestId("reading")).toContainText("Reading the filings…");
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
  "ask-recent": async (page) => {
    await answered(page, question("n01"), 1, "AAPL");
    await answered(page, question("x04"), 1, "AMZN");
    await expect(page.getByTestId("recent").getByRole("button")).toHaveCount(1);
  },
  "ask-stored": async (page) => {
    await answered(page, question("n01"), 1, "AAPL");
    await answered(page, question("x04"), 1, "AMZN");
    await page.getByTestId("recent").getByRole("button").click();
    await expect(page.getByTestId("stored")).toBeVisible();
    await expect(page.locator("#source-1 h4")).toContainText("AAPL");
    await rested(page);
  },
  "ask-refusal": async (page) => {
    await ask(page, question("o02"));
    await expect(page.getByTestId("answer")).toContainText("Not answered");
    await rested(page);
  },
  "ask-error": async (page) => {
    await ask(page, "e2e: switched off");
    await expect(page.getByTestId("ask-error")).toBeVisible();
    await rested(page);
  },
  "ask-sources-failed": async (page) => {
    await page.route("**/api/sources", (route) => route.abort());
    await ask(page, question("n01"));
    await expect(page.getByTestId("sources-error")).toBeVisible();
    await rested(page);
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

/** Ask's sequence on the moving stage, one shot a step: Playwright's clock holds the page's timers and frames still
    between shots, so each step is caught where it is (CSS and Web Animations run on, and are shot finished). */
async function sequence(page: Page, name: string) {
  const shot = (step: string) => page.screenshot({ path: `${DIR}/ask-sequence-${step}-${name}.png`, animations: "disabled" });
  let release = () => {};
  const held = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/sources", async (route) => {
    await held;
    await route.continue();
  });
  await page.clock.install();
  await openAsk(page);
  await expect(page.locator(".stage-field canvas")).toHaveCount(1, { timeout: 15_000 });
  const looked = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/sources");
  await page.getByLabel("Your question").fill(question("x04"));
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await looked;
  await page.clock.runFor(1500); // the membrane gathers round the card while the sources are held
  await shot("1-reading");
  // Just ahead of the page's own clock: a longer jump would run the sources lookup's 6 s timeout out.
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 50);
  release();
  await expect(page.locator(".stage")).toHaveAttribute("data-phase", "pulling");
  for (const [step, ms] of [["2-pull", 400], ["3-read-as", 420], ["4-passages", 220], ["5-answer", 220], ["6-check", 220], ["7-done", 1500]] as const) {
    await page.clock.runFor(ms);
    await shot(step);
  }
  await page.getByLabel("Your question").fill(question("n01"));
  await page.getByLabel("Your question").press("Enter");
  await page.clock.runFor(200);
  await shot("8-leaving");
}

if (MOTION && WIDTHS) {
  for (const width of WIDTHS.filter((each) => each >= 1024)) {
    for (const colorScheme of ["light", "dark"] as const) {
      test(`ask-sequence ${width}-${colorScheme}`, async ({ page }) => {
        test.setTimeout(90_000);
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme, reducedMotion: "no-preference" });
        await sequence(page, `${width}-${colorScheme}`);
      });
    }
  }
}

for (const variant of VARIANTS) {
  test.describe(variant.name, () => {
    test.use({ viewport: variant.viewport, colorScheme: variant.colorScheme, reducedMotion: variant.reducedMotion });
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

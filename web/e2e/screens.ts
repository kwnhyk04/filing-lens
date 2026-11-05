// Every screen in light, dark and phone width, for comparing designs side by side. Each passes axe
// first, then goes to docs/screenshots/ui/<screen>-<variant>.png, or into SCREENS_DIR when that is set.
// SCREENS_WIDTHS (such as "1280,1440,1920,390") shoots each width in light and dark instead, as
// <screen>-<width>-<theme>.png. SCREENS_MOTION=1 shoots its desktop widths with motion allowed, so on a
// graphics card (E2E_CHANNEL=msedge) Ask's moving stage plays: each Ask screen then waits for it.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { ENTER_MS, LEAVE_MS, RELEASE_MS } from "../lib/stage.ts";
import { OFFLINE, OWN_DATA_QUESTION, question } from "./env.ts";
import { audit, expect, signIn, test } from "./fixtures.ts";

const DIR = process.env.SCREENS_DIR ?? "../docs/screenshots/ui";
const TOP_ONLY = new Set(["offline"]); // below its banner it is the demo page, shot in full as "demo"
const SECTION: Record<string, string> = { "landing-results": "#results" }; // shot alone, so a phone's cards read

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

/** The moving stage at rest: its field faded in, the reveal over, the sources let go and nothing moving any more;
    the calm stage at once. */
async function rested(page: Page) {
  if (!(await moving(page))) return;
  await expect(page.locator(".stage-field canvas")).toHaveCount(1, { timeout: 15_000 });
  await expect(page.locator(".stage")).toHaveAttribute("data-phase", /^(empty|done|failed)$/, { timeout: 30_000 });
  await expect(page.locator(".stage .pb-stage")).toHaveAttribute("data-calm", "", { timeout: 15_000 });
}

/** An answer whose card `n` has loaded its source, which names `ticker`. */
async function answered(page: Page, text: string, n: number, ticker: string) {
  await ask(page, text);
  await expect(page.locator(`#source-${n} h4`)).toContainText(ticker);
  await rested(page);
}

/** Coverage's page 2 at 10 a page, then 20 a page: the first row stays on screen, on page 1 of 2. */
async function newSize(page: Page, path: string) {
  await page.goto(path);
  await page.getByLabel("Results per page").selectOption("20");
  await expect(page.getByText("Page 1 of 2", { exact: true })).toBeVisible();
  await expect(page.locator("tbody tr")).toHaveCount(20);
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
  "landing-results": (page) => signedOut(page, "/"),
  "landing-signed-out": async (page) => {
    await signedOut(page, "/?signed-out=1");
    await expect(page.getByRole("status").filter({ hasText: "You're signed out." })).toBeVisible();
  },
  ask: async (page) => {
    await openAsk(page);
    await rested(page);
  },
  "ask-focused": async (page) => {
    await openAsk(page);
    await rested(page);
    await page.getByLabel("Your question").focus();
  },
  "ask-typing": async (page) => {
    await openAsk(page);
    await rested(page);
    await page.getByLabel("Your question").fill("What was Apple's total revenue in");
  },
  "ask-own-data": async (page) => {
    await ask(page, OWN_DATA_QUESTION);
    await expect(page.getByTestId("own-data")).toBeVisible();
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
    await expect(page.locator("tbody tr")).toHaveCount(10);
  },
  "coverage-page-2": async (page) => {
    await page.goto("/coverage");
    await page.getByRole("button", { name: "Go to next page" }).click();
    await expect(page.getByText("Page 2 of 3", { exact: true })).toBeVisible();
  },
  "coverage-size": (page) => newSize(page, "/coverage?page=2&size=10"),
  "coverage-loading": async (page) => {
    await page.goto("/coverage?after=e2e-slow", { waitUntil: "commit" }); // the mock answers after 3 s
    await expect(page.getByTestId("coverage-skeleton")).toBeVisible();
  },
  demo: (page) => signedOut(page, "/demo"),
  "demo-coverage": (page) => signedOut(page, "/demo/coverage"),
  "demo-coverage-page-2": async (page) => {
    await signedOut(page, "/demo/coverage");
    await page.getByRole("button", { name: "Go to next page" }).click();
    await expect(page.getByText("Page 2 of 3", { exact: true })).toBeVisible();
  },
  "demo-coverage-size": async (page) => {
    await page.context().clearCookies();
    await newSize(page, "/demo/coverage?page=2&size=10");
  },
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

/** The card's newest part, by the reveal's order (lib/stage.ts): "reading" before the first, "source-2" for a second. */
const newest = (page: Page) =>
  page.evaluate(() => {
    const card = document.querySelector(".stage .answer-card");
    const order = [
      ["read", ".read-as"], ["source", ".story-passages li"], ["filings", ".card-filings"], ["heading", ".reply-head"],
      ["sentence", ".answer-text [data-sentence]:not([data-later])"], ["check", "[data-tone='check']"], ["table", ".checks"],
      ["warnings", ".warnings"], ["note", ".note"], ["foot", ".card-foot"],
    ];
    const [name, selector] = order.filter(([, each]) => card?.querySelector(each)).at(-1) ?? ["reading", ""];
    const count = selector ? card!.querySelectorAll(selector).length : 0;
    return count > 1 ? `${name}-${count}` : name;
  });

/** Ask's sequence on the moving stage, one shot a step, for question `id`: Playwright's clock holds the page's timers
    and frames still between shots, so each step is caught where it is. CSS and Web Animations (each part's way in)
    run on real time: each shot waits them out, then lets one frame paint, so the membrane holds the card as shot. */
async function sequence(page: Page, name: string, id: string) {
  let shots = 0;
  const shot = async (step: string) => {
    const at = String(++shots).padStart(2, "0");
    await page.screenshot({ path: `${DIR}/ask-sequence-${id}-${name}-${at}-${step}.png`, animations: "disabled", fullPage: true });
  };
  const stage = page.locator(".stage");
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
  await page.getByLabel("Your question").fill(question(id));
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await looked;
  await page.clock.runFor(1500); // the membrane gathers round the card while the sources are held
  await shot("reading");
  // Just ahead of the page's own clock: a longer jump would run the sources lookup's 6 s timeout out.
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 50);
  release();
  await expect(stage).toHaveAttribute("data-phase", "pulling");
  await page.clock.runFor(350);
  await shot("pull");
  for (let step = 1; step < 40; step++) {
    for (let i = 0; i < 40 && Number(await stage.getAttribute("data-step")) < step; i++) await page.clock.runFor(20);
    await page.waitForTimeout(500); // the card grows to take the part, on real time
    await page.clock.runFor(60); // a few frames: the membrane holds the card as it now is, and the field fits the stage
    await shot(await newest(page));
    if ((await stage.getAttribute("data-phase")) === "done") break;
  }
  await page.clock.runFor(1500);
  await shot("done");
  await page.getByLabel("Your question").fill(question(id === "n01" ? "x04" : "n01"));
  await page.getByLabel("Your question").press("Enter");
  await page.clock.runFor(200);
  await shot("leaving");
}

/** Two questions in a row on the moving stage (Apple, then the user's Alphabet against Meta), each answer shot as its
    card settles with its sources held, as they let go a second later, once they have drifted home, and 5 s after the
    card settled, when nothing moves. The page's clock is held between shots, as in `sequence`. */
async function twoInARow(page: Page, name: string) {
  let shots = 0;
  const shot = async (step: string) => {
    await page.waitForTimeout(500); // CSS and Web Animations run on real time
    await page.clock.runFor(60); // a few frames: the membrane and the field paint as they now are
    const at = String(++shots).padStart(2, "0");
    await page.screenshot({ path: `${DIR}/ask-release-${name}-${at}-${step}.png`, animations: "disabled", fullPage: true });
  };
  const stage = page.locator(".stage");
  await page.clock.install();
  await openAsk(page);
  await expect(page.locator(".stage-field canvas")).toHaveCount(1, { timeout: 15_000 });
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 50); // just ahead: see `sequence`
  for (const id of ["n01", "c02"]) {
    await page.getByLabel("Your question").fill(question(id));
    await page.getByLabel("Your question").press("Enter");
    await page.clock.runFor(LEAVE_MS + 50); // the card on screen clears first
    await expect(stage).toHaveAttribute("data-phase", /^(pulling|revealing)$/); // the answer and its sources are in
    for (let i = 0; i < 200 && (await stage.getAttribute("data-phase")) !== "done"; i++) await page.clock.runFor(50);
    await page.clock.runFor(ENTER_MS + 300); // the card in place 0.3 s
    await shot(`${id}-held`);
    await page.clock.runFor(RELEASE_MS); // the let-go 0.36 s under way
    await shot(`${id}-letting-go`);
    await page.clock.runFor(1_300); // let go and drifted home
    await shot(`${id}-released`);
    await page.clock.runFor(2_600); // 5.4 s after the card settled
    await shot(`${id}-still`);
  }
}

/** The landing hero's bar, which the moving story types into: Playwright's clock holds it before the first letter,
    then part way through the question. It takes no focus, so these are its two states. */
async function landingBar(page: Page, name: string) {
  const shot = (state: string) => page.screenshot({ path: `${DIR}/landing-bar-${name}-${state}.png`, animations: "disabled" });
  await page.clock.install();
  await signedOut(page, "/");
  await expect(page.locator(".pb-capsule")).toBeAttached({ timeout: 15_000 });
  await page.clock.pauseAt((await page.evaluate(() => Date.now())) + 50); // just ahead: see `sequence`
  const capsule = page.locator(".pb-capsule");
  for (let i = 0; i < 100 && Number(await capsule.evaluate((bar) => getComputedStyle(bar).opacity)) < 1; i++) await page.clock.runFor(30);
  await expect(page.locator(".pb-typed")).toHaveText(""); // faded in, before the first letter
  await shot("empty");
  for (let i = 0; i < 100 && ((await page.locator(".pb-typed").textContent()) ?? "").length < 16; i++) await page.clock.runFor(30);
  await shot("typing");
}

if (MOTION && WIDTHS) {
  for (const width of WIDTHS.filter((each) => each >= 1024)) {
    for (const colorScheme of ["light", "dark"] as const) {
      test(`landing-bar ${width}-${colorScheme}`, async ({ page }) => {
        test.setTimeout(60_000);
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme, reducedMotion: "no-preference" });
        await landingBar(page, `${width}-${colorScheme}`);
      });
      for (const id of ["n01", "x04"]) {
        test(`ask-sequence ${id} ${width}-${colorScheme}`, async ({ page }) => {
          test.setTimeout(120_000);
          await page.setViewportSize({ width, height: 900 });
          await page.emulateMedia({ colorScheme, reducedMotion: "no-preference" });
          await sequence(page, `${width}-${colorScheme}`, id);
        });
      }
      test(`ask-release ${width}-${colorScheme}`, async ({ page }) => {
        test.setTimeout(120_000);
        await page.setViewportSize({ width, height: 900 });
        await page.emulateMedia({ colorScheme, reducedMotion: "no-preference" });
        await twoInARow(page, `${width}-${colorScheme}`);
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
        if (SECTION[screen]) {
          // Without the fixed header, which would cover the part scrolled under it (a style tag would break the CSP).
          await page.locator(".landing-head").evaluate((head: HTMLElement) => void (head.style.visibility = "hidden"));
          await page.locator(SECTION[screen]).screenshot({ path, animations: "disabled" });
        } else await page.screenshot({ path, fullPage: !TOP_ONLY.has(screen), animations: "disabled" });
      });
    }
  });
}

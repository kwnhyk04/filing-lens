// The suite's `test`: any CSP violation on a page fails the test that opened it, and each signed-in
// test runs as a sign-in of its own, so no test sees another's recent questions.
import AxeBuilder from "@axe-core/playwright";
import { test as base, expect, type BrowserContext, type Page } from "@playwright/test";

import { softwareRenderer } from "../lib/motion.ts";
import { signSession } from "../lib/session.ts";
import { PASSWORD, SESSION_COOKIE, SESSION_SECRET } from "./env.ts";

const WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22a", "wcag22aa"];

/** axe on the page as it stands: any WCAG 2.2 A or AA violation fails. */
export async function audit(page: Page) {
  const { violations } = await new AxeBuilder({ page }).withTags(WCAG).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((node) => node.target.join(" ")).join(", ")}`)).toEqual([]);
}

/** The page fits its phone's width (390 px unless the test sets another) without scrolling sideways. */
export async function noSidewaysScroll(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(page.viewportSize()?.width ?? 390);
}

/**
 * A new sign-in (a new session id) in place of the stored cookie, as signing in would make it; it skips
 * the sign-in form, whose limiter allows 5 tries in 15 minutes. Returns the new cookie's value.
 */
export async function newSignIn(context: BrowserContext): Promise<string> {
  const stored = (await context.cookies()).find((cookie) => cookie.name === SESSION_COOKIE);
  if (!stored) throw new Error("newSignIn needs a signed-in context");
  const value = signSession(SESSION_SECRET, Date.now());
  await context.addCookies([{ ...stored, value }]);
  return value;
}

export const test = base.extend<{ cspGuard: void; freshSession: void }>({
  freshSession: [
    async ({ context }, use) => {
      const signedIn = (await context.cookies()).some((cookie) => cookie.name === SESSION_COOKIE);
      if (signedIn) await newSignIn(context);
      await use();
    },
    { auto: true },
  ],
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

/**
 * On a desktop with a graphics card Ask's moving stage loads after the page (hero-motion.tsx), and its start-up
 * (WebGL, then the field's three.js) can hold a quick draft's first paint for a moment: wait until it is in, so no
 * test races it. Elsewhere the stage stays calm and there is nothing to wait for.
 */
export async function stageReady(page: Page) {
  const renderer = await page.evaluate(() => {
    const desktop = "(min-width: 64rem) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)";
    if (!matchMedia(desktop).matches) return null;
    const gl = document.createElement("canvas").getContext("webgl");
    const info = gl?.getExtension("WEBGL_debug_renderer_info");
    const name = gl ? String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : null;
    gl?.getExtension("WEBGL_lose_context")?.loseContext();
    return name;
  });
  if (!renderer || softwareRenderer(renderer)) return;
  await expect(page.locator(".stage")).toHaveAttribute("data-live", "on", { timeout: 15_000 });
  await expect(page.locator(".stage-field canvas")).toHaveCount(1, { timeout: 15_000 });
}

/** The card's parts as the reveal brings them, in the hero's order (lib/stage.ts's revealParts). */
const PARTS = {
  read: ".read-as",
  source1: ".story-passages li:nth-child(1)",
  source2: ".story-passages li:nth-child(2)",
  filings: ".card-filings",
  heading: ".reply-head",
  sentence1: ".answer-text [data-sentence='1']:not([data-later])",
  sentence2: ".answer-text [data-sentence='2']:not([data-later])",
  check: "[data-tone='check']",
  table: ".checks",
  foot: ".card-foot",
};
export type Part = keyof typeof PARTS;

/** From now on the page notes when each of the card's parts first shows, in ms from this call. */
export async function watchParts(page: Page) {
  await page.evaluate((parts) => {
    const seen: Record<string, number> = {};
    const start = performance.now();
    const look = () => {
      for (const [name, selector] of Object.entries(parts)) {
        if (!(name in seen) && document.querySelector(`.stage .answer-card ${selector}`)) seen[name] = performance.now() - start;
      }
    };
    new MutationObserver(look).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-later"] });
    (window as unknown as { partsSeen: typeof seen }).partsSeen = seen;
  }, PARTS);
}

export const partsSeen = (page: Page) => page.evaluate(() => (window as unknown as { partsSeen: Partial<Record<Part, number>> }).partsSeen);

/** `parts` showed in this order, each at least `gap` ms after the one before, the last before `within` ms. */
export function inOrder(seen: Partial<Record<Part, number>>, parts: Part[], { gap, within }: { gap: number; within: number }) {
  expect(parts.filter((part) => seen[part] === undefined), "parts that never showed").toEqual([]);
  const times = parts.map((part) => seen[part]!);
  times.slice(1).forEach((at, i) => expect(at - times[i], `${parts[i]} to ${parts[i + 1]}`).toBeGreaterThanOrEqual(gap));
  expect(times.at(-1), `${parts.at(-1)} showed`).toBeLessThan(within);
}

/** From now on the page notes each phase Ask's stage passes through, in order. */
export async function recordPhases(page: Page) {
  await page.evaluate(() => {
    const stage = document.querySelector(".stage")!;
    const phases = [stage.getAttribute("data-phase") ?? ""];
    new MutationObserver(() => {
      const phase = stage.getAttribute("data-phase") ?? "";
      if (phase !== phases.at(-1)) phases.push(phase);
    }).observe(stage, { attributes: true, attributeFilter: ["data-phase"] });
    (window as unknown as { phases: string[] }).phases = phases;
  });
}

export const phasesSeen = (page: Page) => page.evaluate(() => (window as unknown as { phases: string[] }).phases);

export async function ask(page: Page, question: string) {
  await page.goto("/ask");
  await stageReady(page);
  await page.getByLabel("Your question").fill(question);
  await page.getByRole("button", { name: "Ask", exact: true }).click(); // not "Ask again"
}

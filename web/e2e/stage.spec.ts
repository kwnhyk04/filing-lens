// Ask's stage, the live version of the landing hero: the field at its top while it is empty; on send the field
// hides and the question takes the top in the card's bubble; once the answer is done the field comes back under the
// card. Recent questions and Sources sit below only when they hold something. On a graphics card the moving stage
// plays the same sequence; elsewhere (CI's software renderer, phones, reduced motion) the calm version stays.
import { randomUUID } from "node:crypto";

import type { Page } from "@playwright/test";

import { softwareRenderer } from "../lib/motion.ts";
import { ENTER_MS } from "../lib/stage.ts";
import { question, snapshot } from "./env.ts";
import { ask, audit, expect, inOrder, noSidewaysScroll, partsSeen, phasesSeen, recordPhases, test, watchParts } from "./fixtures.ts";

const N01 = question("n01");
const X04 = question("x04");
const EXAMPLES = snapshot.answers.filter((item) => !item.answer.refused).map((item) => item.question).slice(0, 4);
const READING = "Reading the filings…";
const stage = (page: Page) => page.locator(".stage");
const box = (page: Page) => page.getByLabel("Your question");
const top = async (page: Page, selector: string) => (await stage(page).locator(selector).boundingBox())!.y - (await stage(page).boundingBox())!.y;

/** The WebGL renderer the page would draw with, or null without WebGL. */
const rendererOf = (page: Page) =>
  page.evaluate(() => {
    const gl = document.createElement("canvas").getContext("webgl");
    const info = gl?.getExtension("WEBGL_debug_renderer_info");
    return gl ? String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER)) : null;
  });

/** The second question of a page, from the field under the answer. */
async function askAgain(page: Page, text: string) {
  await box(page).fill(text);
  await box(page).press("Enter");
}

test("empty: example questions as chips and the field at the top of the stage; no empty cards below", async ({ page }) => {
  await page.goto("/ask");
  await expect(stage(page).getByTestId("samples").getByRole("button")).toHaveText(EXAMPLES);
  await expect(box(page)).toHaveAttribute("placeholder", "Ask about a company's 10-K...");
  await expect(stage(page).getByRole("button", { name: "Ask", exact: true })).toBeVisible();
  expect(await top(page, ".stage-input")).toBeLessThan(60);
  await expect(page.getByTestId("sources-card")).toHaveCount(0);
  await expect(page.getByTestId("recent-card")).toHaveCount(0); // a new sign-in has asked nothing
  await audit(page);
});

test("on send the field hides and the question takes the top in its bubble; nothing is claimed while it reads; then the field comes back under the card", async ({ page }) => {
  const slow = `e2e: slow ${randomUUID()}`; // the mock drafts it for about 3 s, then completes it as o02's refusal
  await page.goto("/ask");
  await box(page).fill(slow);
  await box(page).press("Enter");
  await expect(stage(page).locator(".story-sent")).toHaveText(slow);
  await expect(box(page)).toBeHidden();
  await expect(stage(page)).toHaveAttribute("data-phase", "reading");
  await expect(stage(page).getByText(READING)).toBeVisible();
  await expect(stage(page).locator(".stage-covered li")).toHaveCount(11); // the coverage list's filings, none lit
  await expect(stage(page).locator(".story-passages li, .card-filings li")).toHaveCount(0);
  await expect(page.getByTestId("draft")).toHaveCount(0);
  expect(await top(page, ".story-sent")).toBeLessThan(100);
  await expect(page.getByTestId("answer")).toContainText("Not answered", { timeout: 15_000 });
  await expect(stage(page).getByText(READING)).toHaveCount(0);
  await expect(box(page)).toBeVisible();
  await expect(box(page)).toHaveValue("");
  const [card, field] = await Promise.all([stage(page).locator(".answer-card"), stage(page).locator(".stage-input")].map((part) => part.boundingBox()));
  expect(field!.y).toBeGreaterThan(card!.y + card!.height);
});

test("Enter sends and Shift+Enter starts a new line; under 3 characters nothing is sent", async ({ page }) => {
  const sent: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/answers") sent.push(request.postData() ?? "");
  });
  await page.goto("/ask");
  await box(page).pressSequentially("ab");
  await box(page).press("Enter");
  expect(await box(page).evaluate((element) => (element as HTMLTextAreaElement).validity.tooShort)).toBe(true);
  await expect(page.locator("#question-help")).toContainText("3 to 1,000 characters");
  await box(page).fill("");
  await box(page).pressSequentially("What was Apple's");
  await box(page).press("Shift+Enter");
  await box(page).pressSequentially("revenue?");
  await expect(box(page)).toHaveValue("What was Apple's\nrevenue?");
  expect(sent).toEqual([]);
  await box(page).press("Enter");
  await expect.poll(() => sent.length).toBe(1);
});

test("the answer fills the stage and its sources the Sources card; New question brings the field back at the top; a recent question fills the stage again", async ({ page }) => {
  await ask(page, N01);
  await expect(stage(page).getByTestId("answer")).toContainText("416,161,000,000 USD");
  await expect(stage(page).getByTestId("read-as")).toBeVisible();
  await expect(stage(page).locator("[data-tone='check']")).toBeVisible();
  await expect(stage(page).locator(".story-passages li")).toHaveCount(1);
  await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
  await page.getByRole("button", { name: "New question" }).click();
  await expect(stage(page).locator(".story-sent")).toHaveCount(0);
  await expect(stage(page).getByTestId("samples")).toBeVisible();
  await expect(box(page)).toBeFocused();
  expect(await top(page, ".stage-input")).toBeLessThan(60);
  await expect(page.getByTestId("sources-card")).toHaveCount(0);
  await page.getByTestId("recent").getByRole("button").filter({ hasText: N01 }).click();
  await expect(stage(page).locator(".story-sent")).toHaveText(N01);
  await expect(box(page)).toHaveValue("");
  await expect(page.getByTestId("stored")).toBeVisible();
  await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
});

test("a new question after an answer: the card clears first, then the new question takes the top", async ({ page }) => {
  await ask(page, N01);
  await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
  await recordPhases(page);
  await askAgain(page, X04);
  await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AMZN");
  await expect(stage(page).locator(".story-sent")).toHaveText(X04);
  const phases = await phasesSeen(page);
  expect(phases.slice(0, 3)).toEqual(["done", "leaving", "reading"]);
  expect(phases.at(-1)).toBe("done");
});

test.describe("with reduced motion", () => {
  test.use({ reducedMotion: "reduce" });

  test("a new question replaces the answer at once, with no leave", async ({ page }) => {
    await ask(page, N01);
    await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
    await recordPhases(page);
    await askAgain(page, X04);
    await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AMZN");
    expect(await phasesSeen(page)).not.toContain("leaving");
  });
});

const BAR = {
  light: { bar: "rgb(240, 242, 238)", ink: "rgb(27, 31, 29)", soft: "rgb(95, 103, 99)", arrow: "rgb(255, 255, 255)" },
  dark: { bar: "rgb(31, 36, 34)", ink: "rgb(230, 233, 231)", soft: "rgb(154, 163, 158)", arrow: "rgb(25, 29, 27)" },
};

for (const colorScheme of ["light", "dark"] as const) {
  test(`the Ask bar reaches the page in its neutral greys, in ${colorScheme}`, async ({ page }) => {
    const want = BAR[colorScheme];
    await page.emulateMedia({ colorScheme, reducedMotion: "reduce" });
    await page.goto("/ask");
    const [bar, field, send] = [page.locator(".stage-input"), page.getByLabel("Your question"), page.locator(".stage-send")];
    await expect(bar).toHaveCSS("background-color", want.bar);
    await expect(field).toHaveCSS("color", want.ink);
    expect(await field.evaluate((box) => getComputedStyle(box, "::placeholder").color)).toBe(want.soft);
    await expect(send).toHaveCSS("background-color", want.soft);
    await expect(send).toHaveCSS("border-top-color", want.soft);
    await expect(send).toHaveCSS("color", want.arrow);
    await field.focus();
    await expect(bar).toHaveCSS("outline-color", want.soft);
    await page.keyboard.press("Tab");
    await expect(send).toBeFocused();
    await expect(send).toHaveCSS("outline-color", want.soft);
  });
}

test("Recent questions and Sources sit under the stage, 60 to 40 and top-aligned; a lone one takes the row; under 1024 px Sources comes first", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await ask(page, N01);
  await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
  const [below, lone] = await Promise.all([page.locator(".ask-below"), page.getByTestId("sources-card")].map((part) => part.boundingBox()));
  expect(lone!.width).toBeCloseTo(below!.width, 0);
  await askAgain(page, X04);
  await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AMZN");
  await expect(page.getByTestId("recent").getByRole("button")).toHaveCount(1);
  const boxes = () =>
    Promise.all([stage(page), page.getByTestId("recent-card"), page.getByTestId("sources-card")].map((part) => part.boundingBox()));
  const [stageBox, recent, sources] = await boxes();
  expect(recent!.y).toBeGreaterThan(stageBox!.y + stageBox!.height);
  expect(sources!.y).toBeCloseTo(recent!.y, 0);
  expect(sources!.x).toBeGreaterThan(recent!.x + recent!.width);
  expect(recent!.width / (recent!.width + sources!.width)).toBeCloseTo(0.6, 1);
  await page.setViewportSize({ width: 1000, height: 800 });
  const [, narrowRecent, narrowSources] = await boxes();
  expect(narrowSources!.y + narrowSources!.height).toBeLessThanOrEqual(narrowRecent!.y);
  await page.setViewportSize({ width: 390, height: 844 });
  await noSidewaysScroll(page);
});

test("from 64rem a long Sources card scrolls in itself, and nothing inside it stretches the page", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await ask(page, question("c12")); // four sources, two of them long passages
  await expect(page.getByTestId("sources-card").locator("#source-4 h4")).toContainText("TSLA");
  const sources = page.getByTestId("sources-card").locator(".sources");
  expect(await sources.evaluate((element) => element.scrollHeight > element.clientHeight)).toBe(true);
  // Its visually hidden text once stretched the page about 2,900 px past its end.
  expect(await page.evaluate(() => document.documentElement.scrollHeight - document.body.scrollHeight)).toBe(0);
});

test("a software renderer keeps the calm stage: no canvas and no moving parts", async ({ page }) => {
  await page.goto("/ask");
  const renderer = await rendererOf(page);
  test.skip(!!renderer && !softwareRenderer(renderer), "this checks the path without a graphics card");
  await expect(stage(page)).toHaveAttribute("data-motion", "still", { timeout: 15_000 });
  await expect(page.locator("canvas")).toHaveCount(0);
});

test.describe("on a desktop with a graphics card", () => {
  test.use({ reducedMotion: "no-preference" });

  async function moving(page: Page) {
    await page.goto("/ask");
    const renderer = await rendererOf(page);
    test.skip(!renderer || softwareRenderer(renderer), "the moving stage needs WebGL on a graphics card");
    await expect(stage(page)).toHaveAttribute("data-motion", "live", { timeout: 15_000 });
  }

  /** Holds the sources lookup until `release` is called. */
  async function holdSources(page: Page) {
    let release = () => {};
    const held = new Promise<void>((resolve) => (release = resolve));
    await page.route("**/api/sources", async (route) => {
      await held;
      await route.continue();
    });
    const looked = page.waitForRequest((request) => new URL(request.url()).pathname === "/api/sources");
    return { looked, release: () => release() };
  }

  const things = (page: Page) => page.locator(".stage .pb-thing:not([data-empty='true'])");

  test("while it reads only covered filings float, none reached or lit; once the sources are in, the cited one is pulled in and the parts follow in order", async ({ page }) => {
    test.setTimeout(60_000);
    await moving(page); // first: a skip must come before any request is awaited
    const sources = await holdSources(page);
    await recordPhases(page);
    await box(page).fill(X04);
    await box(page).press("Enter");
    await sources.looked; // the checked answer is in; its sources are held
    await expect(stage(page)).toHaveAttribute("data-phase", "reading");
    await expect(stage(page).getByText(READING)).toBeVisible();
    await expect(things(page)).toHaveCount(11);
    await expect(things(page).filter({ hasNotText: "Filing" })).toHaveCount(0);
    await expect(page.getByTestId("answer")).toHaveCount(0);
    await watchParts(page);
    sources.release();
    await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AMZN");
    inOrder(await partsSeen(page), ["read", "source1", "filings", "heading", "sentence1", "sentence2", "check", "foot"], { gap: 180, within: 3_000 });
    const phases = await phasesSeen(page);
    for (const [before, after] of [["reading", "pulling"], ["pulling", "revealing"], ["revealing", "done"]]) {
      expect(phases.indexOf(before)).toBeLessThan(phases.indexOf(after));
    }
    const cited = page.locator(".stage .pb-thing[data-kind='passage']");
    await expect(cited).toHaveCount(1);
    await expect(cited).toContainText("Item 1");
    await expect(cited).toContainText("AMZN 10-K FY2025");
  });

  /** Every WebGL canvas keeps its last frame, so the test can read what the membrane drew. */
  async function keepFrames(page: Page) {
    await page.addInitScript(() => {
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, type: string, options?: WebGLContextAttributes) {
        return original.call(this, type, type === "webgl" ? { ...options, preserveDrawingBuffer: true } : options);
      } as typeof original;
    });
  }

  /** From now on, after every frame, the page notes each bottom corner and middle of the card the membrane leaves
      uncovered (by the alpha it drew there), from the first part to the end; `uncovered` checks every part's corners. */
  async function watchCover(page: Page) {
    await page.evaluate(() => {
      const stage = document.querySelector<HTMLElement>(".stage")!;
      const canvas = stage.querySelector<HTMLCanvasElement>(".pb-membrane canvas")!;
      const gl = canvas.getContext("webgl")!;
      const pixel = new Uint8Array(4);
      const covered = (x: number, y: number) => {
        const box = canvas.getBoundingClientRect();
        const px = Math.round(((x - box.left) * canvas.width) / box.width), py = Math.round(canvas.height - ((y - box.top) * canvas.height) / box.height);
        gl.readPixels(px, py, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
        return pixel[3] > 200;
      };
      const corners = (r: DOMRect) => [[r.left + 2, r.top + 2], [r.right - 2, r.top + 2], [r.left + 2, r.bottom - 2], [r.right - 2, r.bottom - 2]];
      const misses: string[] = [];
      const check = () => {
        const card = stage.querySelector(".answer-card");
        if (!card || !["revealing", "done"].includes(stage.dataset.phase ?? "")) return;
        const r = card.getBoundingClientRect();
        for (const [x, y] of [[r.left + 2, r.bottom - 2], [r.left + r.width / 2, r.bottom - 2], [r.right - 2, r.bottom - 2]]) {
          if (!covered(x, y)) misses.push(`${stage.dataset.phase} at step ${stage.dataset.step}: the card's bottom at ${Math.round(x)}, ${Math.round(y)}`);
        }
      };
      const frame = () => {
        setTimeout(check); // after the frame, so the membrane and the card are read for the same moment
        requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
      const parts = [".read-as", ".story-passages li", ".card-filings", ".reply-head", ".story-reply", "[data-tone='check']", ".checks", ".card-foot"];
      Object.assign(window, {
        misses,
        uncovered: () =>
          parts.flatMap((selector) =>
            Array.from(stage.querySelectorAll(`.answer-card ${selector}`)).flatMap((part) =>
              corners(part.getBoundingClientRect()).some(([x, y]) => !covered(x, y)) ? [selector] : [],
            ),
          ),
      });
    });
  }
  const misses = (page: Page) => page.evaluate(() => (window as unknown as { misses: string[] }).misses);
  const uncovered = (page: Page) => page.evaluate(() => (window as unknown as { uncovered: () => string[] }).uncovered());

  for (const id of ["n01", "x04"]) {
    test(`the membrane wraps the whole card at every step of the reveal, after it, and once its sources let go (${id})`, async ({ page }) => {
      test.setTimeout(60_000);
      await keepFrames(page);
      await moving(page);
      const sources = await holdSources(page);
      await box(page).fill(question(id));
      await box(page).press("Enter");
      await sources.looked;
      await watchCover(page);
      sources.release();
      await expect(page.getByTestId("sources-card")).toBeVisible();
      await expect(stage(page)).toHaveAttribute("data-phase", "done");
      await page.waitForTimeout(1_500); // the membrane long settled round the answer
      expect(await misses(page)).toEqual([]);
      expect(await uncovered(page)).toEqual([]);
      await page.waitForTimeout(2_500); // its sources let go, and the stage comes to rest
      expect(await misses(page)).toEqual([]);
      expect(await uncovered(page)).toEqual([]);
    });
  }

  /** Each floating bubble and whether the membrane holds it: the alpha drawn at its blob (the pocket a held source
      sits in) and halfway between it and the card's nearer edge (the tendril). Needs keepFrames. */
  const holds = (page: Page) =>
    page.evaluate(() => {
      const stage = document.querySelector<HTMLElement>(".stage")!;
      const canvas = stage.querySelector<HTMLCanvasElement>(".pb-membrane canvas")!;
      const gl = canvas.getContext("webgl")!;
      const box = canvas.getBoundingClientRect(), card = stage.querySelector(".answer-card")!.getBoundingClientRect();
      const pixel = new Uint8Array(4);
      const covered = (x: number, y: number) => {
        gl.readPixels(Math.round(((x - box.left) * canvas.width) / box.width), Math.round(canvas.height - ((y - box.top) * canvas.height) / box.height), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
        return pixel[3] > 200;
      };
      return Array.from(stage.querySelectorAll<HTMLElement>(".pb-thing:not([data-empty='true'])"), (thing) => {
        const blob = thing.querySelector(".pb-thing-shape")!.getBoundingClientRect();
        const x = blob.left + blob.width / 2, y = blob.top + blob.height / 2;
        const edge = { x: x < card.left ? card.left : card.right, y: Math.min(card.bottom - 16, Math.max(card.top + 16, y)) };
        return { kind: thing.dataset.kind, pocket: covered(x, y), tendril: covered((x + edge.x) / 2, (y + edge.y) / 2) };
      });
    });
  const cited = async (page: Page) => (await holds(page)).filter((thing) => thing.kind !== "filing");

  test("two questions in a row: about a second after each card settles its sources let go, the tendrils draw back and the bubbles drift home, so the next question starts from a clean orbit", async ({ page }) => {
    test.setTimeout(90_000);
    await keepFrames(page);
    await moving(page);
    // The user's production check: an answer first, then Alphabet against Meta, whose two facts stayed held.
    for (const [id, count] of [["n01", 1], ["c02", 2]] as const) {
      const sources = await holdSources(page);
      await box(page).fill(question(id));
      await box(page).press("Enter");
      await sources.looked;
      await page.waitForTimeout(1_500); // the membrane gathered round the card, or kept it
      const free = { kind: "filing", pocket: false, tendril: false };
      expect.soft(await holds(page), `${id} while it reads: every bubble a filing, none held`).toEqual(Array(11).fill(free));
      sources.release();
      await expect(stage(page)).toHaveAttribute("data-phase", "done");
      const done = Date.now();
      await page.waitForTimeout(ENTER_MS + 300); // the card in place, its sources still held
      expect.soft(await cited(page), `${id}: held as its card settles`).toEqual(Array(count).fill({ kind: "fact", pocket: true, tendril: true }));
      await page.waitForTimeout(done + ENTER_MS + 2_800 - Date.now()); // a second more, then the let-go
      expect.soft(await cited(page), `${id}: let go about a second after its card settled`).toEqual(Array(count).fill({ kind: "fact", pocket: false, tendril: false }));
      await page.unroute("**/api/sources");
    }
  });

  /** Whether the floating bubbles moved over 0.7 s, once what changed them has settled. */
  async function drifting(page: Page) {
    await page.waitForTimeout(300);
    const spots = () => things(page).evaluateAll((all) => all.map((thing) => (thing as HTMLElement).style.transform));
    const before = await spots();
    await page.waitForTimeout(700);
    return JSON.stringify(await spots()) !== JSON.stringify(before);
  }

  /** Whether nothing on screen moves: the membrane, the field, the bubbles, the eyes. Two pictures a second apart. */
  async function still(page: Page) {
    const first = await page.screenshot();
    await page.waitForTimeout(1_000);
    return first.equals(await page.screenshot());
  }

  test("the stage moves only while it answers and as the answer settles: still within 5 s of the page load and of the card settling; scrolled away or in a hidden tab it stops", async ({ page }) => {
    test.setTimeout(90_000);
    await moving(page);
    await expect(stage(page)).toHaveAttribute("data-live", "on");
    await page.waitForFunction(() => performance.now() > 5_000, undefined, { timeout: 15_000 });
    expect(await still(page), "the empty stage, 5 s after the page loaded").toBe(true);
    const sources = await holdSources(page);
    await askAgain(page, N01);
    await sources.looked;
    expect(await drifting(page), "while it reads").toBe(true);
    await page.evaluate(() => {
      document.body.style.paddingBottom = "300vh";
      window.scrollTo(0, document.body.scrollHeight);
    });
    expect(await drifting(page), "scrolled away").toBe(false);
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await drifting(page), "back in view").toBe(true);
    const visibility = (state: string) =>
      page.evaluate((value) => {
        Object.defineProperty(document, "visibilityState", { configurable: true, get: () => value });
        document.dispatchEvent(new Event("visibilitychange"));
      }, state);
    await visibility("hidden");
    expect(await drifting(page), "a hidden tab").toBe(false);
    await visibility("visible");
    expect(await drifting(page), "visible again").toBe(true);
    sources.release();
    await expect(stage(page)).toHaveAttribute("data-phase", "done");
    const done = Date.now();
    await page.waitForTimeout(1_500);
    expect(await drifting(page), "as its sources let go").toBe(true);
    await page.waitForTimeout(done + ENTER_MS + 5_000 - Date.now());
    expect(await still(page), "5 s after the card settled").toBe(true);
  });

  test("Ask's stage has no Pause button: its motion stops by itself", async ({ page }) => {
    await moving(page);
    await expect(stage(page)).toHaveAttribute("data-live", "on");
    await expect(page.getByRole("button", { name: /motion/i })).toHaveCount(0);
  });

  test("a recent question shows its card whole, with no pull", async ({ page }) => {
    test.setTimeout(60_000);
    await moving(page);
    await askAgain(page, N01);
    await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
    await askAgain(page, X04);
    await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AMZN");
    await recordPhases(page);
    await page.getByTestId("recent").getByRole("button").filter({ hasText: N01 }).click();
    await expect(page.getByTestId("stored")).toBeVisible();
    await expect(page.getByTestId("sources-card").locator("#source-1 h4")).toContainText("AAPL");
    const phases = await phasesSeen(page);
    expect(phases).not.toContain("pulling");
    expect(phases).not.toContain("revealing");
  });
});

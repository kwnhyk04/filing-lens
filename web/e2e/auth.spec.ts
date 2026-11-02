import type { BrowserContext } from "@playwright/test";

import { SESSION_TTL_S, signSession } from "../lib/session.ts";
import { question, SESSION_COOKIE, SESSION_SECRET } from "./env.ts";
import { ask, expect, signedOut, signIn, test } from "./fixtures.ts";

const UNAUTHORIZED = { status: 401, json: { code: "unauthorized", detail: "Sign in first." } };

/** The stored cookie, its token signed `ago` milliseconds back: a genuine token past its end once `ago` passes 8 hours. */
async function signedInAgo(context: BrowserContext, ago: number) {
  const stored = (await context.cookies()).find((cookie) => cookie.name === SESSION_COOKIE);
  if (!stored) throw new Error("signedInAgo needs a signed-in context");
  await context.addCookies([{ ...stored, value: signSession(SESSION_SECRET, Date.now() - ago) }]);
}

test.describe("signed out", () => {
  test.use(signedOut);

  test("a wrong password stays on sign-in, with the error", async ({ page }) => {
    await page.goto("/login");
    await signIn(page, "not the password");
    await expect(page.getByTestId("sign-in-error")).toHaveText("Wrong password.");
    await expect(page).toHaveURL(/\/login$/);
  });

  test("signing in goes on to the page asked for", async ({ page }) => {
    await page.goto("/coverage");
    await expect(page).toHaveURL("/login?next=%2Fcoverage");
    await signIn(page);
    await expect(page).toHaveURL("/coverage");
    await expect(page.getByRole("heading", { level: 1, name: "Coverage" })).toBeVisible();
  });

  test("sign-in offers a way back home", async ({ page }) => {
    await page.goto("/login");
    const back = page.getByRole("link", { name: "Back to home" });
    await expect(back).toHaveAttribute("href", "/");
    await back.click();
    await expect(page).toHaveURL("/");
  });

  test("after signing in, Back skips the sign-in form", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("banner").getByRole("link", { name: "Sign in", exact: true }).click();
    await expect(page).toHaveURL("/login");
    await signIn(page);
    await expect(page).toHaveURL("/ask");
    await page.goBack();
    await expect(page).toHaveURL("/");
    await expect(page.getByLabel("Password")).toHaveCount(0);
  });

  test("next= keeps pages only: a link to sign-out signs in to Ask", async ({ page }) => {
    await page.goto("/login?next=%2Flogout");
    await signIn(page);
    await expect(page).toHaveURL("/ask");
    await expect(page.getByRole("heading", { level: 1, name: "Ask" })).toBeVisible();
  });
});

test("a session that ends while asking signs in again and returns to Ask", async ({ page, context }) => {
  const listed = page.waitForResponse((reply) => new URL(reply.url()).pathname === "/api/recent");
  await page.goto("/ask");
  await listed; // the list's own call, before the session ends
  await context.clearCookies();
  await page.getByLabel("Your question").fill(question("n01"));
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page).toHaveURL("/login?next=%2Fask");
  await signIn(page);
  await expect(page).toHaveURL("/ask");
  await expect(page.getByRole("heading", { level: 1, name: "Ask" })).toBeVisible();
});

test("signing out lands on the landing page with a short notice, the cookie gone and the cache cleared", async ({ page, context }) => {
  await page.goto("/ask");
  const [response] = await Promise.all([
    page.waitForResponse((reply) => new URL(reply.url()).pathname === "/logout"),
    page.getByRole("button", { name: "Sign out" }).click(),
  ]);
  expect(response.status()).toBe(303);
  // allHeaders(): headers() leaves out security-related headers such as this one.
  expect((await response.allHeaders())["clear-site-data"]).toBe('"cache"');
  await expect(page).toHaveURL("/?signed-out=1");
  await expect(page.getByRole("status").filter({ hasText: "You're signed out." })).toBeVisible();
  await expect(page.getByRole("banner").getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
  expect((await context.cookies()).some((cookie) => cookie.name === SESSION_COOKIE)).toBe(false);
});

test("signed in, the logo leads home, whose header offers Ask, and sign-in never shows its form", async ({ page }) => {
  await page.goto("/ask");
  await page.getByRole("banner").getByRole("link", { name: "FilingLens" }).click();
  await expect(page).toHaveURL("/");
  const header = page.getByRole("banner");
  await expect(header.getByRole("link", { name: "Open Ask" })).toHaveAttribute("href", "/ask");
  await expect(header.getByRole("link", { name: "Sign in", exact: true })).toHaveCount(0);
  await expect(page.getByRole("status").filter({ hasText: "signed out" })).toHaveCount(0);
  await page.goto("/?signed-out=1"); // an old link to the notice says nothing to someone signed in
  await expect(page.getByRole("status").filter({ hasText: "signed out" })).toHaveCount(0);
  await page.goto("/login");
  await expect(page).toHaveURL("/ask");
  await expect(page.getByLabel("Password")).toHaveCount(0);
});

test("an expired session shows Sign in, never Sign out", async ({ page, context }) => {
  await signedInAgo(context, SESSION_TTL_S * 1000 + 60_000);
  await page.goto("/");
  await expect(page.getByRole("banner").getByRole("link", { name: "Sign in", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Open Ask" })).toHaveCount(0);
  await page.goto("/demo");
  await expect(page.getByRole("banner").getByRole("link", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  await page.goto("/ask");
  await expect(page).toHaveURL("/login?next=%2Fask");
  await expect(page.getByLabel("Password")).toBeVisible();
});

test("an Ask page left open past its session's end offers Sign in, not Sign out", async ({ page }) => {
  await page.clock.install();
  await page.goto("/ask");
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
  await page.clock.fastForward(SESSION_TTL_S * 1000);
  await expect(page.getByRole("button", { name: "Sign out" })).toHaveCount(0);
  await expect(page.getByRole("banner").getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login?next=%2Fask");
});

// The session ends just as the call goes out: the cookie is gone and the BFF answers 401, as it would.
for (const path of ["recent", "sources"]) {
  test(`a 401 from /api/${path} sends Ask to the sign-in form`, async ({ page, context }) => {
    await page.route(`**/api/${path}`, async (route) => {
      await context.clearCookies();
      await route.fulfill(UNAUTHORIZED);
    });
    if (path === "recent") await page.goto("/ask");
    else await ask(page, question("x04"));
    await expect(page).toHaveURL("/login?next=%2Fask");
    await expect(page.getByLabel("Password")).toBeVisible();
  });
}

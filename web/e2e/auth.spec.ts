import { SESSION_COOKIE } from "./env.ts";
import { expect, signedOut, signIn, test } from "./fixtures.ts";

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
});

test("signing out expires the cookie and clears the browser cache", async ({ page, context }) => {
  await page.goto("/ask");
  const [response] = await Promise.all([
    page.waitForResponse((reply) => new URL(reply.url()).pathname === "/logout"),
    page.getByRole("button", { name: "Sign out" }).click(),
  ]);
  expect(response.status()).toBe(303);
  // allHeaders(): headers() leaves out security-related headers such as this one.
  expect((await response.allHeaders())["clear-site-data"]).toBe('"cache"');
  await expect(page).toHaveURL("/login");
  expect((await context.cookies()).some((cookie) => cookie.name === SESSION_COOKIE)).toBe(false);
});

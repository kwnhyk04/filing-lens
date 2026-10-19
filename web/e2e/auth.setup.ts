import { SESSION_COOKIE, STATE } from "./env.ts";
import { expect, signIn, test as setup } from "./fixtures.ts";

setup("signing in stores the __Host- session cookie on http://127.0.0.1", async ({ page, context }) => {
  await page.goto("/login");
  await signIn(page);
  await expect(page.getByRole("heading", { level: 1, name: "Ask" })).toBeVisible();
  const cookie = (await context.cookies()).find((stored) => stored.name === SESSION_COOKIE);
  expect(cookie, "Chromium keeps a Secure cookie on http://127.0.0.1").toMatchObject({
    domain: "127.0.0.1",
    path: "/",
    httpOnly: true,
    secure: true,
    sameSite: "Lax",
  });
  await context.storageState({ path: STATE });
});

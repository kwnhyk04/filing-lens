// Against the server whose API_URL fails at once: every live page lands on its demo twin.
import { SESSION_COOKIE } from "./env.ts";
import { expect, test } from "./fixtures.ts";

test("a signed-in visitor can sign out from the offline demo", async ({ page, context }) => {
  await page.goto("/");
  await expect(page).toHaveURL("/demo?offline=1");
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL("/login");
  expect((await context.cookies()).some((cookie) => cookie.name === SESSION_COOKIE)).toBe(false);
});

const TWINS: [string, string][] = [
  ["/", "/demo?offline=1"],
  ["/coverage", "/demo/coverage?offline=1"],
  ["/coverage?after=abc", "/demo/coverage?offline=1"],
];

for (const [live, twin] of TWINS) {
  test(`${live} lands on ${twin}, with the offline banner`, async ({ page }) => {
    const response = await page.goto(live);
    expect(response?.status()).toBe(200);
    await expect(page).toHaveURL(twin);
    await expect(page.getByTestId("demo-banner")).toContainText("The live service is offline");
  });
}

test("a cursor the snapshot lacks goes to the demo's first page", async ({ page }) => {
  await page.goto("/demo/coverage?after=999&offline=1");
  await expect(page).toHaveURL("/demo/coverage?offline=1");
  await expect(page.locator("tbody tr")).toHaveCount(20);
});

test("the demo header says what the snapshot covers", async ({ page }) => {
  for (const path of ["/demo", "/demo/coverage"]) {
    await page.goto(path);
    await expect(page.getByRole("banner")).toContainText("30 companies · 30 filings");
  }
});

test("the demo pages its coverage like the live one", async ({ page }) => {
  await page.goto("/demo/coverage");
  await page.getByRole("link", { name: "Next page" }).click();
  await expect(page.locator("tbody tr")).toHaveCount(10);
});

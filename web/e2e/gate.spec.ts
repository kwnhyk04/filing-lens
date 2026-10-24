import { expect, signedOut, test } from "./fixtures.ts";

test.use(signedOut);

for (const path of ["/ask", "/coverage", "/coverage?after=abc", "/no-such-page"]) {
  test(`${path} without a session goes to sign-in`, async ({ page }) => {
    await page.goto(path);
    await expect(page).toHaveURL(`/login?next=${encodeURIComponent(path)}`);
  });
}

test("the BFF routes answer 401 in JSON without a session", async ({ request }) => {
  for (const path of ["/api/answers", "/api/sources"]) {
    const response = await request.post(path, { data: {} });
    expect(response.status()).toBe(401);
    expect(await response.json()).toMatchObject({ code: "unauthorized" });
  }
});

test("the demo needs no session", async ({ page }) => {
  for (const path of ["/demo", "/demo/coverage"]) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.getByTestId("demo-banner")).toBeVisible();
    await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  }
});

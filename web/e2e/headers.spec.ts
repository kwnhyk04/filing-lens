import { API_KEY, LIVE, question } from "./env.ts";
import { ask, expect, test } from "./fixtures.ts";

test("pages carry the CSP, the frame and sniffing guards, and no-store", async ({ page }) => {
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  expect(headers["cache-control"]).toContain("no-store");
  expect(headers["content-security-policy"]).toMatch(/script-src 'self' 'nonce-[A-Za-z0-9+/=]+' 'strict-dynamic'/);
  expect(headers["content-security-policy"]).toContain("connect-src 'self'");
  expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  expect(headers["referrer-policy"]).toBe("no-referrer");
  expect(headers["x-powered-by"]).toBeUndefined();
});

test("BFF replies send no-store, and other origins are refused", async ({ request }) => {
  const data = { chunkIds: [], factIds: [] };
  const same = await request.post("/api/sources", { data, headers: { Origin: LIVE } });
  expect(same.status()).toBe(200);
  expect(same.headers()["cache-control"]).toBe("no-store");
  const missing = await request.post("/api/sources", { data });
  expect(missing.status()).toBe(403);
  const other = await request.post("/api/sources", { data, headers: { Origin: "http://evil.example" } });
  expect(other.status()).toBe(403);
});

test("the API key never reaches the browser", async ({ page }) => {
  const bodies: Promise<string>[] = [];
  page.on("response", (response) => {
    if (/html|javascript|json|event-stream/.test(response.headers()["content-type"] ?? "")) {
      bodies.push(response.text().catch(() => ""));
    }
  });
  for (const path of ["/coverage", "/demo", "/demo/coverage"]) await page.goto(path);
  await ask(page, question("x04"));
  await expect(page.locator("#source-1 mark")).toBeVisible();
  const texts = await Promise.all(bodies);
  expect(texts.length).toBeGreaterThan(5);
  for (const text of texts) expect(text).not.toContain(API_KEY);
});

// Mockup features 2: the router's reading, the number checks, the coverage line, the sample questions
// and the two-thirds layout, live and on the demo, against the snapshot the mock API replays.
import { question, snapshot } from "./env.ts";
import { ask, audit, expect, noSidewaysScroll, test } from "./fixtures.ts";

const ANSWERED = snapshot.answers.filter((item) => !item.answer.refused).map((item) => item.question);
const C12 = ["Comparison", "Tesla, Inc.", "Fiscal 2024 and 2025", "Net income"];

test("the live header says what the API covers, on Ask and on Coverage", async ({ page }) => {
  for (const path of ["/ask", "/coverage"]) {
    await page.goto(path);
    await expect(page.getByRole("banner")).toContainText("30 companies · 30 filings");
  }
});

test("an empty Ask offers the answered saved questions; a click fills the box and asks nothing", async ({ page }) => {
  const asked: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/answers") asked.push(request.url());
  });
  await page.goto("/ask");
  const samples = page.getByTestId("samples").getByRole("button");
  await expect(samples).toHaveText(ANSWERED);
  await samples.first().click();
  const box = page.getByLabel("Your question");
  await expect(box).toHaveValue(ANSWERED[0]);
  await expect(box).toBeFocused();
  expect(asked).toEqual([]);
  await page.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByTestId("answer")).toBeVisible();
  await expect(page.getByTestId("samples")).toHaveCount(0);
  await page.getByRole("button", { name: "New question" }).click();
  await expect(page.getByTestId("samples")).toBeVisible();
});

test("an answer reads as the router read it, each amount checked against its source", async ({ page }) => {
  await ask(page, question("c12"));
  await expect(page.getByTestId("read-as").getByRole("listitem")).toHaveText(C12);
  const checks = page.getByTestId("checks");
  await expect(checks.locator("caption")).toHaveText("Numbers checked against their sources");
  await expect(checks.locator("tbody tr")).toHaveCount(6);
  await expect(checks.locator("tbody tr").nth(2)).toContainText("$3,855 million");
  await expect(checks.locator("tbody tr").nth(2)).toContainText("3,855, as quoted");
  await expect(checks.locator("td.match")).toHaveText(Array(6).fill("Matches"));
  await expect(page.getByTestId("timings")).toContainText("every number checked");
});

test("a fact-only answer is checked against XBRL data; a refusal reads as read and checks nothing", async ({ page }) => {
  await ask(page, question("n01"));
  const checks = page.getByTestId("checks");
  await expect(checks.locator("caption")).toHaveText("Numbers checked against XBRL data");
  await expect(checks.locator("tbody tr")).toContainText("416,161,000,000 USD");
  await ask(page, question("o02"));
  await expect(page.getByTestId("read-as").getByRole("listitem")).toHaveText(["Out of scope"]);
  await expect(page.getByTestId("checks")).toHaveCount(0);
  await expect(page.getByTestId("timings")).not.toContainText("every number checked");
});

test("from 64rem the sources panel takes about a third of the width, beside the answer", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await ask(page, question("x04"));
  await expect(page.locator("#source-1 h4")).toContainText("AMZN");
  const main = await page.locator(".ask-main").boundingBox();
  const panel = await page.locator(".ask > .sources").boundingBox();
  if (!main || !panel) throw new Error("no layout boxes");
  expect(panel.x).toBeGreaterThan(main.x + main.width);
  expect(panel.width / (main.width + panel.width)).toBeCloseTo(1 / 3, 1);
});

test("390 px: the checks table scrolls in its own region, which the keyboard can reach", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await ask(page, question("c12"));
  await expect(page.getByTestId("checks").locator("tbody tr")).toHaveCount(6);
  await noSidewaysScroll(page);
  await audit(page); // axe's scrollable-region-focusable
});

test("the demo shows each saved answer's reading and its number checks", async ({ page }) => {
  await page.goto("/demo");
  const c12 = page.locator("#q-c12");
  await expect(c12.getByTestId("read-as").getByRole("listitem")).toHaveText(C12);
  await expect(c12.getByTestId("checks").locator("tbody tr")).toHaveCount(6);
  await expect(page.locator("#q-n01").getByTestId("checks").locator("caption")).toHaveText(
    "Numbers checked against XBRL data",
  );
  await expect(page.locator("#q-o02").getByTestId("checks")).toHaveCount(0);
});

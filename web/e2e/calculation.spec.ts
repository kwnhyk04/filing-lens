// A comparison whose arithmetic FilingLens did (K1): its card names its two facts, and Ask looks up only those.
import { ask, audit, expect, test } from "./fixtures.ts";

test("a calculation's card names its two facts and passes axe; only the facts are looked up", async ({ page }) => {
  const looked: unknown[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/sources") looked.push(request.postDataJSON());
  });
  await ask(page, "e2e: calculated");
  const card = page.locator("#source-3");
  await expect(card.locator("h4")).toHaveText("Source 3: Calculated by FilingLens from sources 1 and 2");
  await expect(card).toContainText("Alphabet Inc. (GOOGL) is higher by 201,870,000,000 USD, 100.45% more than");
  await expect(page.locator("#source-1 h4")).toContainText("GOOGL fact"); // the facts' cards loaded
  const checks = page.getByTestId("checks");
  await expect(checks.locator("caption")).toHaveText("Numbers checked against XBRL data");
  await expect(checks.locator("tbody tr").nth(2)).toContainText("201,870,000,000, calculated");
  expect(looked).toEqual([{ chunkIds: [], factIds: ["380121", "206185"] }]);
  await audit(page);
  await card.getByRole("link", { name: "source 1", exact: true }).click();
  await expect(page).toHaveURL(/#source-1$/);
});

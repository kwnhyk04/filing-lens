// The site's icons as a signed-out browser fetches them, as iPhone Safari does on a first visit: every icon a
// page links answers without a session, as the type and size its link says, and /favicon.ico, which browsers
// also ask for unlinked, holds the mark at the usual sizes.
import type { Page } from "@playwright/test";

import { faviconSvg } from "../lib/logo.ts";
import { expect, signedOut, test } from "./fixtures.ts";

test.use(signedOut);

const PNG = Buffer.from("89504e470d0a1a0a", "hex");

/** A PNG's size as a link's sizes says it ("180x180"), from its header. */
function pngSize(bytes: Buffer): string {
  expect(bytes.subarray(0, 8)).toEqual(PNG);
  return `${bytes.readUInt32BE(16)}x${bytes.readUInt32BE(20)}`;
}

/** An ICO's frames by size, each checked to be a PNG of the size its entry says. */
function icoSizes(bytes: Buffer): string[] {
  expect([bytes.readUInt16LE(0), bytes.readUInt16LE(2)]).toEqual([0, 1]);
  return Array.from({ length: bytes.readUInt16LE(4) }, (_, i) => {
    const entry = 6 + 16 * i;
    const size = `${bytes[entry] || 256}x${bytes[entry + 1] || 256}`;
    const offset = bytes.readUInt32LE(entry + 12);
    expect(pngSize(bytes.subarray(offset, offset + bytes.readUInt32LE(entry + 8)))).toBe(size);
    return size;
  });
}

/** The icons a page's head links. */
const icons = (page: Page) =>
  page
    .locator("head link[rel~='icon'], head link[rel='apple-touch-icon']")
    .evaluateAll((links) => links.map((link) => Object.fromEntries(["rel", "href", "type", "sizes"].map((name) => [name, link.getAttribute(name)]))));

test("every page links the mark as an SVG, a favicon.ico and a 180 px home-screen icon", async ({ page }) => {
  await page.goto("/");
  const linked = await icons(page);
  expect(linked.map(({ rel, type }) => `${rel} ${type}`).sort()).toEqual(["apple-touch-icon image/png", "icon image/svg+xml", "icon image/x-icon"]);
  // Sized, not "any": the favicon guide Next's docs link gives the ICO a size, so Chrome keeps the SVG.
  expect(linked.find(({ type }) => type === "image/x-icon")?.sizes).toMatch(/^\d+x\d+$/);
  for (const path of ["/login", "/demo"]) {
    await page.goto(path);
    expect(await icons(page)).toEqual(linked);
  }
});

test("each linked icon answers without a session, as the type and size its link says", async ({ page }) => {
  await page.goto("/");
  for (const { href, type, sizes } of await icons(page)) {
    const response = await page.request.get(href!, { maxRedirects: 0 });
    expect(response.status(), href!).toBe(200);
    expect(response.headers()["content-type"], href!).toBe(type);
    const body = await response.body();
    if (type === "image/svg+xml") expect(body.toString("utf8").trim()).toBe(faviconSvg());
    else if (type === "image/x-icon") expect(icoSizes(body)).toEqual(["16x16", "32x32", "48x48"]);
    else expect(pngSize(body)).toBe(sizes);
  }
});

test("/favicon.ico, which browsers ask for unlinked, holds the mark at 16, 32 and 48 px", async ({ request }) => {
  const response = await request.get("/favicon.ico", { maxRedirects: 0 });
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toBe("image/x-icon");
  expect(icoSizes(await response.body())).toEqual(["16x16", "32x32", "48x48"]);
});

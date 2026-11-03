// Coverage's pager under `node --test`: the page numbers round the current page, with "…" only for pages left out,
// and the page and size read from the URL.
import assert from "node:assert/strict";
import { test } from "node:test";

import { DEFAULT_SIZE, PAGE_SIZES, pageHolding, pageItems, pageOf, pageSize } from "./pager.ts";

test("the page numbers: at most five round the current page, '…' only where pages are left out", () => {
  // Origin UI's usePagination marked a gap after the last page whenever every page fit.
  assert.deepEqual(pageItems(1, 3), { pages: [1, 2, 3], left: false, right: false });
  assert.deepEqual(pageItems(1, 5), { pages: [1, 2, 3, 4, 5], left: false, right: false });
  assert.deepEqual(pageItems(1, 10), { pages: [1, 2, 3, 4], left: false, right: true });
  assert.deepEqual(pageItems(5, 10), { pages: [4, 5, 6], left: true, right: true });
  assert.deepEqual(pageItems(10, 10), { pages: [7, 8, 9, 10], left: true, right: false });
  assert.deepEqual(pageItems(1, 1), { pages: [1], left: false, right: false });
  for (let total = 1; total <= 30; total++) {
    for (let current = 1; current <= total; current++) {
      const { pages, left, right } = pageItems(current, total);
      const at = `page ${current} of ${total}`;
      assert.ok(pages.includes(current), at);
      assert.ok(pages.length <= 5, at);
      assert.equal(left, pages[0] > 1, `${at}: a gap on the left only for pages left out`);
      assert.equal(right, pages.at(-1)! < total, `${at}: a gap on the right only for pages left out`);
      pages.slice(1).forEach((page, i) => assert.equal(page, pages[i] + 1, at));
    }
  }
});

test("the size: 10, 20 or 50 a page, from the URL or storage, else none", () => {
  assert.deepEqual(PAGE_SIZES, [10, 20, 50]);
  assert.equal(DEFAULT_SIZE, 10);
  assert.equal(pageSize("20"), 20);
  for (const value of ["7", "0", "", "20abc", "1e1", null, undefined]) assert.equal(pageSize(value), null, String(value));
});

test("the page: the URL's whole number, at most the last page, else the first", () => {
  assert.equal(pageOf("2", 3), 2);
  assert.equal(pageOf("9", 3), 3);
  for (const value of ["0", "-1", "x", "2.5", "", null, undefined]) assert.equal(pageOf(value, 3), 1, String(value));
  assert.equal(pageOf("2", 0), 1); // no rows still has a first page
});

test("a new size goes to the page that holds the row on screen", () => {
  assert.equal(pageHolding(10, 20), 1); // row 11 of page 2 at 10 a page
  assert.equal(pageHolding(10, 10), 2);
  assert.equal(pageHolding(29, 10), 3);
  assert.equal(pageHolding(0, 50), 1);
});

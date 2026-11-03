// Coverage's pager (components/coverage-table.tsx): the sizes it offers, the page and size read from the URL, and
// the page numbers it shows, after Origin UI's usePagination (MIT; docs/third-party.md).

export const PAGE_SIZES = [10, 20, 50] as const;
export type PageSize = (typeof PAGE_SIZES)[number];
export const DEFAULT_SIZE: PageSize = 10;

/** A size the pager offers, from the URL or storage; else null. */
export function pageSize(value: string | null | undefined): PageSize | null {
  return PAGE_SIZES.find((size) => String(size) === value) ?? null;
}

/** The page to show: the URL's whole number, at most the last of `pages`; else the first. */
export function pageOf(value: string | null | undefined, pages: number): number {
  const page = /^\d+$/.test(value ?? "") ? Number(value) : 1;
  return Math.min(Math.max(page, 1), Math.max(pages, 1));
}

/** The page that holds row `index` (from 0) at `size` rows a page. */
export const pageHolding = (index: number, size: number) => Math.floor(index / size) + 1;

/** The page numbers round `current` of `total`, at most `shown`, and whether pages are left out on either side
    ("…"). Origin UI's version also marked a gap when every page fit. */
export function pageItems(current: number, total: number, shown = 5): { pages: number[]; left: boolean; right: boolean } {
  const range = (start: number, end: number) => Array.from({ length: end - start + 1 }, (_, i) => start + i);
  if (total <= shown) return { pages: range(1, total), left: false, right: false };
  const left = current - 1 > shown / 2, right = total - current + 1 > shown / 2;
  const half = Math.floor(shown / 2);
  let start = Math.max(1, current - half), end = Math.min(total, current + half);
  if (start === 1) end = shown;
  if (end === total) start = total - shown + 1;
  if (left) start++;
  if (right) end--;
  return { pages: range(start, end), left, right };
}

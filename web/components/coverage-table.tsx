"use client";
// Companies and their filings in Origin UI's table with numeric pagination (21st.dev, MIT; docs/third-party.md),
// ported into the app's CSS; the live and demo coverage pages share it, each passing every company. The page and
// the size live in the URL (?page=&size=), so a refresh, Back and a shared link keep them, and the size is
// remembered for the next visit. On a phone each company is a card, and the pager keeps Previous, Next and the size.
// Each filing shown is indexed, since the API lists no other status.
import { useSearchParams } from "next/navigation";
import { type ReactNode, useEffect, useLayoutEffect, useRef } from "react";

import { formLabel } from "../lib/answer.ts";
import type { Company } from "../lib/demo.ts";
import { DEFAULT_SIZE, PAGE_SIZES, pageHolding, pageItems, pageOf, pageSize } from "../lib/pager.ts";

// Lucide's chevron-left, chevron-right, chevron-down and ellipsis (ISC licence, docs/third-party.md).
const LEFT = <path d="m15 18-6-6 6-6" />;
const RIGHT = <path d="m9 18 6-6-6-6" />;
const DOWN = <path d="m6 9 6 6 6-6" />;
const MORE = (
  <>
    <circle cx="12" cy="12" r="1" />
    <circle cx="19" cy="12" r="1" />
    <circle cx="5" cy="12" r="1" />
  </>
);

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      {children}
    </svg>
  );
}

const STORED = "fl-coverage-size";
/** The size this browser chose last, where storage allows. */
function storedSize() {
  try {
    return pageSize(localStorage.getItem(STORED));
  } catch {
    return null;
  }
}
function store(size: number) {
  try {
    localStorage.setItem(STORED, String(size));
  } catch {
    // blocked storage: the choice lasts this visit, in the URL
  }
}

export function CoverageTable({ companies }: { companies: Company[] }) {
  const params = useSearchParams();
  const size = pageSize(params.get("size")) ?? DEFAULT_SIZE;
  const pages = Math.max(1, Math.ceil(companies.length / size));
  const page = pageOf(params.get("page"), pages);
  const { pages: numbers, left, right } = pageItems(page, pages);
  const body = useRef<HTMLTableSectionElement>(null);
  const kept = useRef<{ cik: string; top: number } | null>(null); // the row a new size keeps where it was

  /** To `next` at `nextSize`, in the URL, other parameters (the demo's offline flag) kept. */
  function go(next: number, nextSize: number, how: "pushState" | "replaceState" = "pushState") {
    const query = new URLSearchParams(params.toString());
    query.set("page", String(next));
    query.set("size", String(nextSize));
    window.history[how](null, "", `?${query}`);
  }

  // On arrival: the size remembered from a visit before when the link names none, and the URL set to the page shown
  // (a page past the end shows the last).
  useEffect(() => {
    const remembered = params.has("size") ? null : storedSize();
    if (remembered && remembered !== size) go(pageHolding((page - 1) * size, remembered), remembered, "replaceState");
    else if (params.has("page") && params.get("page") !== String(page)) go(page, size, "replaceState");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** A new size: remembered, on the page that holds the first row on screen, which stays where it was. */
  function resize(nextSize: number) {
    store(nextSize);
    const rows = Array.from(body.current?.rows ?? []);
    const index = Math.max(0, rows.findIndex((row) => row.getBoundingClientRect().bottom > 0));
    const row = rows[index];
    if (row) kept.current = { cik: row.dataset.cik ?? "", top: row.getBoundingClientRect().top };
    go(pageHolding((page - 1) * size + index, nextSize), nextSize);
  }
  useLayoutEffect(() => {
    const was = kept.current;
    kept.current = null;
    const row = was && body.current?.querySelector(`[data-cik="${was.cik}"]`);
    if (row) window.scrollBy(0, row.getBoundingClientRect().top - was.top);
  }, [size]);

  return (
    <>
      <div className="data-frame">
        <div className="data-scroll" role="region" aria-labelledby="coverage-caption" tabIndex={0}>
          <table className="data-table cards">
            <caption id="coverage-caption" className="visually-hidden">
              Companies and their indexed filings
            </caption>
            <thead>
              <tr>
                <th scope="col">Company</th>
                <th scope="col">CIK</th>
                <th scope="col">Filings</th>
              </tr>
            </thead>
            <tbody ref={body}>
              {companies.slice((page - 1) * size, page * size).map((company) => (
                <tr key={company.cik} data-cik={company.cik}>
                  <th scope="row">
                    {company.name} <span className="ticker">({company.ticker})</span>
                  </th>
                  <td className="cik">
                    <span className="card-label">CIK</span>
                    {company.cik}
                  </td>
                  <td>
                    <ul className="filings">
                      {company.filings.edges.map(({ node: filing }) => (
                        <li key={filing.accessionNumber}>
                          <a href={filing.url}>
                            {formLabel(filing.formType)} FY{filing.fiscalYear}
                            {filing.fiscalPeriod === "FY" ? "" : ` ${filing.fiscalPeriod}`}
                          </a>
                          , filed {filing.filedOn} <span className="badge ok">Indexed</span>
                        </li>
                      ))}
                      {company.filings.edges.length === 0 && <li>None indexed yet</li>}
                      {company.filings.pageInfo.hasNextPage && <li>Older filings are not listed</li>}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="pager">
        <p className="pager-status" aria-live="polite">
          Page <span>{page}</span> of <span>{pages}</span>
        </p>
        <nav aria-label="Pages" className="pager-pages">
          <ul>
            <li>
              <button
                type="button"
                className="pager-button outline"
                aria-label="Go to previous page"
                aria-disabled={page === 1 || undefined}
                onClick={() => page > 1 && go(page - 1, size)}
              >
                <Icon>{LEFT}</Icon>
              </button>
            </li>
            {left && (
              <li className="pager-number">
                <span className="pager-gap" aria-hidden="true">
                  <Icon>{MORE}</Icon>
                </span>
              </li>
            )}
            {numbers.map((number) => (
              <li key={number} className="pager-number">
                <button
                  type="button"
                  className={number === page ? "pager-button outline" : "pager-button"}
                  aria-label={`Page ${number}`}
                  aria-current={number === page ? "page" : undefined}
                  onClick={() => go(number, size)}
                >
                  {number}
                </button>
              </li>
            ))}
            {right && (
              <li className="pager-number">
                <span className="pager-gap" aria-hidden="true">
                  <Icon>{MORE}</Icon>
                </span>
              </li>
            )}
            <li>
              <button
                type="button"
                className="pager-button outline"
                aria-label="Go to next page"
                aria-disabled={page === pages || undefined}
                onClick={() => page < pages && go(page + 1, size)}
              >
                <Icon>{RIGHT}</Icon>
              </button>
            </li>
          </ul>
        </nav>
        <div className="pager-size">
          <label htmlFor="page-size" className="visually-hidden">
            Results per page
          </label>
          <span className="pager-select">
            <select id="page-size" value={size} onChange={(event) => resize(Number(event.target.value))}>
              {PAGE_SIZES.map((each) => (
                <option key={each} value={each}>
                  {each} / page
                </option>
              ))}
            </select>
            <Icon>{DOWN}</Icon>
          </span>
        </div>
      </div>
    </>
  );
}

/** The table's shape while the API answers: its frame, head and a page of rows as bars, then the pager's. */
export function CoverageSkeleton() {
  const bars = (
    <>
      <span />
      <span />
      <span />
    </>
  );
  return (
    <div data-testid="coverage-skeleton" aria-busy="true">
      <p className="visually-hidden">Loading the companies…</p>
      <div className="data-frame skeleton" aria-hidden="true">
        <div className="skeleton-head">{bars}</div>
        {Array.from({ length: DEFAULT_SIZE }, (_, i) => (
          <div key={i} className="skeleton-row">
            {bars}
          </div>
        ))}
      </div>
      <div className="pager skeleton" aria-hidden="true">
        {bars}
      </div>
    </div>
  );
}

// Companies and their filings, with keyset paging links; the live and demo coverage pages share it. In the
// app's list look, after FreightAudit's (docs/design.md): on a phone each company is a card. Each filing shown is
// indexed, since the API lists no other status.
import Link from "next/link";

import { formLabel } from "../lib/answer.ts";
import type { Company } from "../lib/demo.ts";

// Lucide's chevrons-left and chevron-right (ISC licence, docs/third-party.md).
const FIRST = "m11 17-5-5 5-5M18 17l-5-5 5-5";
const NEXT = "m9 18 6-6-6-6";

function Arrow({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d={d} />
    </svg>
  );
}

export function CoverageTable({ companies, first, next }: { companies: Company[]; first?: string; next?: string }) {
  return (
    <>
      <div className="table-wrap" role="region" aria-labelledby="coverage-caption" tabIndex={0}>
        <table className="list-table cards">
          <caption id="coverage-caption">Companies and their indexed filings</caption>
          <thead>
            <tr>
              <th scope="col">Company</th>
              <th scope="col">CIK</th>
              <th scope="col">Filings</th>
            </tr>
          </thead>
          <tbody>
            {companies.map((company) => (
              <tr key={company.cik}>
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
      <nav aria-label="Pages" className="pager">
        {first && (
          <Link href={first} className="button secondary small">
            <Arrow d={FIRST} />
            First page
          </Link>
        )}
        {next && (
          <Link href={next} className="button secondary small">
            Next page
            <Arrow d={NEXT} />
          </Link>
        )}
      </nav>
    </>
  );
}

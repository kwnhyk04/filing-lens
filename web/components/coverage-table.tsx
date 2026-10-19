// Companies and their filings, with keyset paging links; the live and demo coverage pages share it.
import Link from "next/link";

import { formLabel } from "../lib/answer.ts";
import type { Company } from "../lib/demo.ts";

export function CoverageTable({ companies, first, next }: { companies: Company[]; first?: string; next?: string }) {
  return (
    <>
      <div className="scroll" role="region" aria-labelledby="coverage-caption" tabIndex={0}>
        <table>
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
                  {company.name} ({company.ticker})
                </th>
                <td>{company.cik}</td>
                <td>
                  <ul className="filings">
                    {company.filings.edges.map(({ node: filing }) => (
                      <li key={filing.accessionNumber}>
                        <a href={filing.url}>
                          {formLabel(filing.formType)} FY{filing.fiscalYear}
                          {filing.fiscalPeriod === "FY" ? "" : ` ${filing.fiscalPeriod}`}
                        </a>
                        , filed {filing.filedOn}
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
      <nav aria-label="Pages" className="pages">
        {first && <Link href={first}>First page</Link>}
        {next && <Link href={next}>Next page</Link>}
      </nav>
    </>
  );
}

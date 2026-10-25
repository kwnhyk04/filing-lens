// The header's coverage line: from the API's totals on live pages, from the snapshot on the demo.

const counted = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/** "30 companies · 30 filings", with "+" after the filings when more exist than were counted. */
export function coverageLine(companies: number, filings: number, more = false): string {
  const filed = counted(filings, "filing", "filings").replace(" ", more ? "+ " : " ");
  return `${counted(companies, "company", "companies")} · ${filed}`;
}

import { redirect } from "next/navigation";
import { Suspense } from "react";

import { ConfigError, LiveHeader } from "../../components/chrome.tsx";
import { CoverageSkeleton, CoverageTable } from "../../components/coverage-table.tsx";
import { coverageLine } from "../../lib/coverage.ts";
import { coverageAll, requireSession } from "../../lib/server.ts";

export const metadata = { title: "Coverage" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

/** The header and the table's skeleton at once; the companies follow when the API answers. */
export default async function CoveragePage({ searchParams }: Props) {
  const { expiresAt } = await requireSession();
  const { after } = await searchParams;
  const loading = (
    <>
      <LiveHeader page="coverage" expiresAt={expiresAt} />
      <main id="main">
        <h1>Coverage</h1>
        <CoverageSkeleton />
      </main>
    </>
  );
  return (
    <Suspense fallback={loading}>
      <Coverage after={typeof after === "string" ? after : undefined} expiresAt={expiresAt} />
    </Suspense>
  );
}

/** Every company from the API, paged on the page; `after`, an old pager's cursor, starts the list after it. */
async function Coverage({ after, expiresAt }: { after?: string; expiresAt: number }) {
  const list = await coverageAll(after);
  if (!list.ok) {
    const { failure } = list;
    if (failure.kind === "offline") redirect("/demo/coverage?offline=1");
    if (failure.kind === "misconfigured") {
      return (
        <>
          <LiveHeader page="coverage" expiresAt={expiresAt} />
          <ConfigError requestId={failure.requestId} />
        </>
      );
    }
    if (failure.code === "invalid_input") redirect("/coverage"); // a cursor the API does not know
    throw new Error(`Coverage failed: ${failure.code}`);
  }
  const { companies, totals } = list.data;
  return (
    <>
      <LiveHeader page="coverage" line={coverageLine(totals.companies, totals.filings)} expiresAt={expiresAt} />
      <main id="main">
        <h1>Coverage</h1>
        <CoverageTable companies={companies} />
      </main>
    </>
  );
}

import { redirect } from "next/navigation";

import { ConfigError, LiveHeader } from "../../components/chrome.tsx";
import { CoverageTable } from "../../components/coverage-table.tsx";
import { coveragePage, requireSession } from "../../lib/server.ts";

export const metadata = { title: "Coverage" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function CoveragePage({ searchParams }: Props) {
  await requireSession();
  const { after } = await searchParams;
  const cursor = typeof after === "string" ? after : undefined;
  const page = await coveragePage(cursor);
  if (!page.ok) {
    const { failure } = page;
    if (failure.kind === "offline") redirect("/demo/coverage?offline=1");
    if (failure.kind === "misconfigured") {
      return (
        <>
          <LiveHeader page="coverage" />
          <ConfigError requestId={failure.requestId} />
        </>
      );
    }
    if (failure.code === "invalid_input") redirect("/coverage"); // a cursor the API does not know
    throw new Error(`Coverage failed: ${failure.code}`);
  }
  const { edges, pageInfo } = page.data.companies;
  return (
    <>
      <LiveHeader page="coverage" />
      <main id="main">
        <h1>Coverage</h1>
        <CoverageTable
          companies={edges.map((edge) => edge.node)}
          first={cursor ? "/coverage" : undefined}
          next={pageInfo.hasNextPage && pageInfo.endCursor ? `/coverage?after=${encodeURIComponent(pageInfo.endCursor)}` : undefined}
        />
      </main>
    </>
  );
}

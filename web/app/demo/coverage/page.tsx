import { redirect } from "next/navigation";

import { DemoBanner, DemoHeader } from "../../../components/chrome.tsx";
import { CoverageTable } from "../../../components/coverage-table.tsx";
import { demoCoverage } from "../../../lib/demo.ts";

export const metadata = { title: "Demo: coverage" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function DemoCoveragePage({ searchParams }: Props) {
  const { after, offline } = await searchParams;
  const companies = demoCoverage(typeof after === "string" ? after : undefined);
  if (!companies) redirect(`/demo/coverage${offline === "1" ? "?offline=1" : ""}`); // a cursor the snapshot lacks
  return (
    <>
      <DemoHeader page="coverage" />
      <main id="main">
        <DemoBanner offline={offline === "1"} />
        <h1>Coverage</h1>
        <CoverageTable companies={companies} />
      </main>
    </>
  );
}

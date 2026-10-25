import { redirect } from "next/navigation";

import { Ask } from "../../components/ask.tsx";
import { ConfigError, LiveHeader } from "../../components/chrome.tsx";
import { coverageLine } from "../../lib/coverage.ts";
import { demo } from "../../lib/demo.ts";
import { ping, requireSession } from "../../lib/server.ts";

export const metadata = { title: "Ask" };

// The saved answers' questions that were answered: the corpus holds what they need.
const SAMPLES = demo.answers.filter((item) => !item.answer.refused).map((item) => item.question);

export default async function AskPage() {
  await requireSession();
  const api = await ping();
  if (!api.ok && api.failure.kind === "offline") redirect("/demo?offline=1");
  const line = api.ok ? coverageLine(api.data.totals.companies, api.data.totals.filings) : undefined;
  return (
    <>
      <LiveHeader page="ask" line={line} />
      {!api.ok && api.failure.kind === "misconfigured" ? (
        <ConfigError requestId={api.failure.requestId} />
      ) : (
        <main id="main">
          <h1>Ask</h1>
          <Ask samples={SAMPLES} />
        </main>
      )}
    </>
  );
}

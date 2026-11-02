import { redirect } from "next/navigation";

import { Ask } from "../../components/ask.tsx";
import { ConfigError, LiveHeader } from "../../components/chrome.tsx";
import { coverageLine } from "../../lib/coverage.ts";
import { demo } from "../../lib/demo.ts";
import { coveragePage, requireSession } from "../../lib/server.ts";
import { coveredThings } from "../../lib/stage.ts";
import "./ask.css";

export const metadata = { title: "Ask" };

// Four of the saved answers' questions that were answered: the corpus holds what they need.
const SAMPLES = demo.answers.filter((item) => !item.answer.refused).map((item) => item.question).slice(0, 4);

export default async function AskPage() {
  await requireSession();
  // One call, as the totals' was: the coverage list's first page carries the totals and the filings that float
  // round the stage while an answer is on its way.
  const api = await coveragePage();
  if (!api.ok && api.failure.kind === "offline") redirect("/demo?offline=1");
  const line = api.ok ? coverageLine(api.data.totals.companies, api.data.totals.filings) : undefined;
  const covered = api.ok ? coveredThings(api.data.companies.edges.map((edge) => edge.node)) : [];
  return (
    <>
      <LiveHeader page="ask" line={line} />
      {!api.ok && api.failure.kind === "misconfigured" ? (
        <ConfigError requestId={api.failure.requestId} />
      ) : (
        <main id="main">
          <h1>Ask</h1>
          <Ask samples={SAMPLES} covered={covered} />
        </main>
      )}
    </>
  );
}

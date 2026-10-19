import { redirect } from "next/navigation";

import { Ask } from "../components/ask.tsx";
import { ConfigError, LiveHeader } from "../components/chrome.tsx";
import { ping, requireSession } from "../lib/server.ts";

export const metadata = { title: "Ask" };

export default async function AskPage() {
  await requireSession();
  const api = await ping();
  if (!api.ok && api.failure.kind === "offline") redirect("/demo?offline=1");
  return (
    <>
      <LiveHeader page="ask" />
      {!api.ok && api.failure.kind === "misconfigured" ? (
        <ConfigError requestId={api.failure.requestId} />
      ) : (
        <main id="main">
          <h1>Ask</h1>
          <Ask />
        </main>
      )}
    </>
  );
}

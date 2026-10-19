"use client";
import Link from "next/link";

export default function ErrorPage({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  return (
    <main id="main" className="narrow">
      <title>Error · FilingLens</title>
      <h1>Something went wrong</h1>
      <p>
        This page could not be shown{error.digest ? ` (reference ${error.digest})` : ""}.
      </p>
      <p>
        <button type="button" onClick={() => retry()}>
          Try again
        </button>{" "}
        or <Link href="/demo">see the demo</Link>.
      </p>
    </main>
  );
}

import Link from "next/link";

export default function NotFound() {
  return (
    <main id="main" className="narrow">
      <title>Not found · FilingLens</title>
      <h1>Page not found</h1>
      <p>Nothing lives at this address.</p>
      <p>
        <Link href="/ask">Ask a question</Link> or <Link href="/demo">see the demo</Link>.
      </p>
    </main>
  );
}

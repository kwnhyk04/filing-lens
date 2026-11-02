// Page chrome: the signed-in and demo headers, the demo banner, the configuration-error page. The
// landing page's header is landing-header.tsx; both carry its theme switch.
import { cookies } from "next/headers";
import Link from "next/link";

import { demo, demoCoverageLine } from "../lib/demo.ts";
import { hasSession } from "../lib/server.ts";
import { THEME_COOKIE, themeOf } from "../lib/theme.ts";
import { ThemeToggle } from "./theme-toggle.tsx";

const current = (on: boolean) => (on ? ("page" as const) : undefined);

/** The theme switch, set to the choice the fl-theme cookie keeps, as the root layout reads it. */
async function Theme() {
  return <ThemeToggle theme={themeOf((await cookies()).get(THEME_COOKIE)?.value)} />;
}

function SignOut() {
  return (
    <form action="/logout" method="post">
      <button type="submit" className="secondary small">
        Sign out
      </button>
    </form>
  );
}

/** `line`: what the API's totals say is covered; left out when the API did not answer. */
export function LiveHeader({ page, line }: { page: "ask" | "coverage"; line?: string }) {
  return (
    <header className="site">
      <Link href="/" className="brand" prefetch={false}>
        FilingLens
      </Link>
      <nav aria-label="Main">
        <Link href="/ask" aria-current={current(page === "ask")} prefetch={false}>
          Ask
        </Link>
        <Link href="/coverage" aria-current={current(page === "coverage")} prefetch={false}>
          Coverage
        </Link>
      </nav>
      <div className="site-end">
        {line && <p>{line}</p>}
        <Theme />
        <SignOut />
      </div>
    </header>
  );
}

/** Signed in, it offers Sign out: while the API is offline, the demo is the only page there is. */
export async function DemoHeader({ page }: { page: "answers" | "coverage" }) {
  const signedIn = await hasSession();
  return (
    <header className="site">
      <Link href="/demo" className="brand">
        FilingLens
      </Link>
      <nav aria-label="Demo">
        <Link href="/demo" aria-current={current(page === "answers")}>
          Saved answers
        </Link>
        <Link href="/demo/coverage" aria-current={current(page === "coverage")}>
          Coverage
        </Link>
      </nav>
      {/* Counted from the snapshot; the live header's line comes from the API's totals. */}
      <div className="site-end">
        <p>{demoCoverageLine}</p>
        <Theme />
        {signedIn ? (
          <SignOut />
        ) : (
          <Link href="/login" className="button small" prefetch={false}>
            Sign in
          </Link>
        )}
      </div>
    </header>
  );
}

export function DemoBanner({ offline }: { offline: boolean }) {
  return (
    <div className={offline ? "banner offline" : "banner"} role="note" data-testid="demo-banner">
      {offline && (
        <p>
          <strong>The live service is offline,</strong> so you are seeing the saved demo.
        </p>
      )}
      <p>
        <strong>Demo.</strong> {demo.source} Nothing on these pages calls a model or the live API.
      </p>
    </div>
  );
}

export function ConfigError({ requestId }: { requestId?: string }) {
  return (
    <main id="main" className="narrow">
      <h1>Configuration error</h1>
      <p data-testid="config-error">
        The API refused this web server&apos;s key, so nothing can be shown. Tell the operator, with
        the request id <code>{requestId ?? "unknown"}</code>.
      </p>
    </main>
  );
}

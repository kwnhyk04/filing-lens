import Link from "next/link";
import { redirect } from "next/navigation";

import { safeNext } from "../../lib/guards.ts";
import { hasSession } from "../../lib/server.ts";
import { SignInForm } from "./form.tsx";

export const metadata = { title: "Sign in" };

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function LoginPage({ searchParams }: Props) {
  const { next } = await searchParams;
  const target = safeNext(typeof next === "string" ? next : null) ?? "/";
  if (await hasSession()) redirect(target);
  return (
    <main id="main" className="narrow">
      <h1>Sign in to FilingLens</h1>
      <SignInForm next={target} />
      <p>
        No password? <Link href="/demo">See the demo</Link>: saved questions with their recorded,
        cited answers. It needs no sign-in.
      </p>
    </main>
  );
}

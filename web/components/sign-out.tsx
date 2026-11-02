"use client";
// Sign out while the sign-in lasts; once it has ended, a Sign in link back to this page, so a page left open
// never offers to sign out a session that is already over. Checked again when Back or Forward restores it.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

export function SignOut({ expiresAt }: { expiresAt: number }) {
  const [ended, setEnded] = useState(false);
  const path = usePathname();

  useEffect(() => {
    const check = () => setEnded(Date.now() >= expiresAt);
    check();
    const timer = window.setTimeout(check, Math.max(0, expiresAt - Date.now())); // 8 hours at most
    window.addEventListener("pageshow", check);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pageshow", check);
    };
  }, [expiresAt]);

  if (ended) {
    return (
      <Link href={`/login?next=${encodeURIComponent(path)}`} className="button small" prefetch={false}>
        Sign in
      </Link>
    );
  }
  return (
    <form action="/logout" method="post">
      <button type="submit" className="secondary small">
        Sign out
      </button>
    </form>
  );
}

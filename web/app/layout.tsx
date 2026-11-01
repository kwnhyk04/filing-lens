import "./globals.css";

import type { Metadata } from "next";
import { cookies } from "next/headers";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { THEME_COOKIE, themeOf } from "../lib/theme.ts";

export const metadata: Metadata = {
  title: { template: "%s · FilingLens", default: "FilingLens" },
  description: "Answers to analyst questions over SEC filings, with citations you can check.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection(); // every page renders per request, so each gets its CSP nonce
  // Light or Dark from the header's toggle; no attribute means the system's, so nothing flashes either way.
  const theme = themeOf((await cookies()).get(THEME_COOKIE)?.value);
  return (
    <html lang="en" data-theme={theme === "system" ? undefined : theme}>
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}

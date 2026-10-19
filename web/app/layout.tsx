import "./globals.css";

import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: { template: "%s · FilingLens", default: "FilingLens" },
  description: "Answers to analyst questions over SEC filings, with citations you can check.",
};

export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection(); // every page renders per request, so each gets its CSP nonce
  return (
    <html lang="en">
      <body>
        <a className="skip" href="#main">
          Skip to content
        </a>
        {children}
      </body>
    </html>
  );
}

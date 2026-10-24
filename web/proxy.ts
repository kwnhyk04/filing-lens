// Runs before every route: the CSP with a fresh nonce, and the sign-in gate.
import { randomBytes } from "node:crypto";

import { NextResponse, type NextRequest } from "next/server";

import { SESSION_COOKIE, verifySession } from "./lib/session.ts";

const PUBLIC = /^\/$|^\/(login|logout|healthz|readyz)$|^\/demo(\/|$)/;

function policy(nonce: string): string {
  const dev = process.env.NODE_ENV === "development"; // React needs eval for dev error overlays
  return [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ""}`,
    `style-src 'self' 'nonce-${nonce}'`,
    "img-src 'self' data:",
    "font-src 'self'",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ].join("; ");
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (!PUBLIC.test(pathname) && !verifySession(token, process.env.SESSION_SECRET, Date.now())) {
    if (pathname.startsWith("/api/")) {
      const body = { code: "unauthorized", detail: "Sign in first." };
      return NextResponse.json(body, { status: 401, headers: { "Cache-Control": "no-store" } });
    }
    const login = new URL("/login", request.url);
    login.searchParams.set("next", pathname + search);
    return NextResponse.redirect(login);
  }
  const nonce = randomBytes(16).toString("base64");
  const csp = policy(nonce);
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", csp); // Next reads the nonce from it while rendering
  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", csp);
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };

// POST /logout: expires the session cookie and clears the browser's cache of signed-in pages.
import { NextResponse, type NextRequest } from "next/server";

import { isSameOrigin } from "../../lib/guards.ts";
import { json } from "../../lib/server.ts";
import { SESSION_COOKIE } from "../../lib/session.ts";

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request.headers)) {
    return json(403, { code: "forbidden", detail: "Requests from other sites are refused." });
  }
  // A relative Location: Next builds this handler's request URL on localhost, not the host asked.
  const response = new NextResponse(null, { status: 303, headers: { Location: "/login" } });
  response.cookies.set(SESSION_COOKIE, "", { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: 0 });
  response.headers.set("Clear-Site-Data", '"cache"');
  response.headers.set("Cache-Control", "no-store");
  return response;
}

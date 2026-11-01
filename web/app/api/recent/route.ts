// GET /api/recent: this sign-in's recent questions with their stored answers, newest first.
import type { NextRequest } from "next/server";

import { failureResponse, guardApi, json, recentAnswers } from "../../../lib/server.ts";

export async function GET(request: NextRequest) {
  const signedIn = await guardApi(request);
  if (signedIn instanceof Response) return signedIn;
  const page = await recentAnswers(signedIn.sid, request.signal);
  return page.ok ? json(200, page.data) : failureResponse(page.failure);
}

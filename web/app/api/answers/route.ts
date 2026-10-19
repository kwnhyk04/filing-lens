// POST /api/answers: the API's answer stream for a signed-in page, piped through unchanged.
import type { NextRequest } from "next/server";

import { failureResponse, guardApi, json, openAnswerStream } from "../../../lib/server.ts";

export const maxDuration = 45; // the stream's 35 s timeout, with room to spare

export async function POST(request: NextRequest) {
  const refused = await guardApi(request);
  if (refused) return refused;
  const body = (await request.json().catch(() => null)) as { question?: unknown } | null;
  const question = typeof body?.question === "string" ? body.question.trim() : "";
  if (question.length < 3 || question.length > 1000) {
    return json(422, { code: "validation_failed", detail: "Ask a question of 3 to 1,000 characters." });
  }
  const opened = await openAnswerStream(question, request.signal);
  if (!opened.ok) return failureResponse(opened.failure);
  return new Response(opened.data, {
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-store" },
  });
}

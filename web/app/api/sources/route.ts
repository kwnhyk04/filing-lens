// POST /api/sources: the chunks and facts an answer cites, through GraphQL `Sources`.
import type { NextRequest } from "next/server";

import { failureResponse, fetchSources, guardApi, json } from "../../../lib/server.ts";

const MAX_IDS = 200; // an answer cites at most 12 chunks, but one fact per company and year

function ids(value: unknown): string[] | null {
  const valid =
    Array.isArray(value) &&
    value.length <= MAX_IDS &&
    value.every((id) => typeof id === "string" && /^[^\0]{1,64}$/.test(id));
  return valid ? [...new Set(value as string[])] : null;
}

export async function POST(request: NextRequest) {
  const signedIn = await guardApi(request);
  if (signedIn instanceof Response) return signedIn;
  const body = (await request.json().catch(() => null)) as Record<string, unknown> | null;
  const chunkIds = ids(body?.chunkIds);
  const factIds = ids(body?.factIds);
  if (!chunkIds || !factIds) {
    return json(422, { code: "validation_failed", detail: `chunkIds and factIds take up to ${MAX_IDS} ids each.` });
  }
  const sources = await fetchSources(chunkIds, factIds, request.signal);
  return sources.ok ? json(200, sources.data) : failureResponse(sources.failure);
}

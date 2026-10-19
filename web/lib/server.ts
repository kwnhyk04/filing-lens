// Server-only glue: settings, the session check, and the API calls (API_KEY only, each logged).
import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import type { NextRequest } from "next/server";

import {
  ApiError,
  CompaniesDocument,
  CoverageDocument,
  createApiClient,
  executeGraphql,
  SourcesDocument,
  type SourcesQuery,
  type TypedDocumentString,
} from "../../clients/ts/index.ts";
import { classify, failureLabel, type Failure } from "./errors.ts";
import { createLimiter, isSameOrigin } from "./guards.ts";
import { log } from "./log.ts";
import { SESSION_COOKIE, verifySession } from "./session.ts";
import { loadSettings, type Settings } from "./settings.ts";

const PAGE_TIMEOUT_MS = 5_000;
const ANSWER_TIMEOUT_MS = 35_000; // the API's own `failed` event at 30 s arrives first
const MAX_IDS = 20; // per kind in one Sources query

let settings: Settings | undefined;
export const config = (): Settings => (settings ??= loadSettings(process.env));
export const signInLimiter = createLimiter();

export async function hasSession(): Promise<boolean> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  return verifySession(token, config().sessionSecret, Date.now());
}

/** The second lock on every live page; proxy.ts is the first. */
export async function requireSession(): Promise<void> {
  if (!(await hasSession())) redirect("/login");
}

export const json = (status: number, body: object) =>
  Response.json(body, { status, headers: { "Cache-Control": "no-store" } });

/** A BFF route's guard: a same-origin request with a session, else the refusal to send. */
export async function guardApi(request: NextRequest): Promise<Response | null> {
  if (!isSameOrigin(request.headers)) {
    return json(403, { code: "forbidden", detail: "Requests from other sites are refused." });
  }
  if (!(await hasSession())) return json(401, { code: "unauthorized", detail: "Sign in first." });
  return null;
}

/** A failure as the BFF's JSON: `{code, detail, retryAfter, requestId}`. */
export function failureResponse(failure: Failure): Response {
  if (failure.kind === "offline") return json(503, { code: "offline", detail: "The API is offline." });
  if (failure.kind === "misconfigured") {
    const detail = "The web server's API key was rejected.";
    return json(502, { code: "misconfigured", detail, requestId: failure.requestId });
  }
  const { status, code, detail, retryAfterS: retryAfter, requestId } = failure;
  return json(status >= 400 ? status : 502, { code, detail, retryAfter, requestId });
}

export type Result<T> = { ok: true; data: T } | { ok: false; failure: Failure };

async function call<T>(route: string, run: (requestId: string) => Promise<T>): Promise<Result<T>> {
  const requestId = crypto.randomUUID(); // fits the API's [A-Za-z0-9._-]{1,64}, so logs join
  const started = performance.now();
  const ms = () => Math.round(performance.now() - started);
  try {
    const data = await run(requestId);
    log("api_call", { route, status: 200, ms: ms(), request_id: requestId });
    return { ok: true, data };
  } catch (error) {
    const failure = classify(error);
    const { label, level } = failureLabel(error, failure);
    const status = error instanceof ApiError ? error.status : undefined;
    const name = status === undefined ? (error as Error).name : undefined;
    log("api_call", { route, status, failure: label, error: name, ms: ms(), request_id: requestId }, level);
    if (failure.kind === "misconfigured") log("api_key_rejected", { route, status, request_id: requestId }, "error");
    return { ok: false, failure };
  }
}

function graphql<R, V>(document: TypedDocumentString<R, V>, variables: V, requestId: string, signal?: AbortSignal) {
  const { apiUrl, apiKey } = config();
  return executeGraphql(apiUrl, apiKey, document, variables, { signal, requestId, timeoutMs: PAGE_TIMEOUT_MS });
}

/** One company: shows whether the API is up and takes the key. */
export const ping = () => call("ping", (id) => graphql(CompaniesDocument, { first: 1 }, id));

export const coveragePage = (after?: string) =>
  call("coverage", (id) => graphql(CoverageDocument, { first: 20, after }, id));

/** An answer's cited chunks and facts, in queries of at most 20 ids of each kind. */
export function fetchSources(chunkIds: string[], factIds: string[], signal: AbortSignal) {
  return call("sources", async (id) => {
    const sources: SourcesQuery = { chunks: [], facts: [] };
    for (let i = 0; i < Math.max(chunkIds.length, factIds.length); i += MAX_IDS) {
      const ids = { chunkIds: chunkIds.slice(i, i + MAX_IDS), factIds: factIds.slice(i, i + MAX_IDS) };
      const page = await graphql(SourcesDocument, ids, id, signal);
      sources.chunks.push(...page.chunks);
      sources.facts.push(...page.facts);
    }
    return sources;
  });
}

/** The API's answer stream, unchanged; admission errors (429, 503) come back as a failure. */
export function openAnswerStream(question: string, signal: AbortSignal) {
  return call("answers", async (id) => {
    const { apiUrl, apiKey } = config();
    const client = createApiClient(apiUrl, apiKey, ANSWER_TIMEOUT_MS);
    const { data } = await client.POST("/v1/answers/stream", {
      body: { question },
      parseAs: "stream",
      signal,
      headers: { "X-Request-ID": id },
    });
    if (!data) throw new TypeError("The answer stream had no body.");
    return data;
  });
}

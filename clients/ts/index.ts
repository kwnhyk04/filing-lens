// Typed FilingLens clients: REST through openapi-fetch, GraphQL through the generated documents.
// Server-side only: the API key must never reach a browser.
import createClient from "openapi-fetch";

import type { TypedDocumentString } from "./graphql/graphql.ts";
import type { paths } from "./openapi";

export type { components, operations, paths } from "./openapi";
export * from "./graphql/graphql.ts";

const TIMEOUT_MS = 30_000;
const UNEXPECTED = "unexpected_response"; // the code of a reply that is not one of the API's problems

/** A failed call: HTTP status, the API's error code, Retry-After in seconds and the request id. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly retryAfterS: number | undefined;
  readonly requestId: string | undefined;

  constructor(
    status: number,
    code: string,
    detail: string,
    retryAfterS?: number,
    requestId?: string,
  ) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.retryAfterS = retryAfterS;
    this.requestId = requestId;
  }
}

export interface CallOptions {
  /** The caller's signal, such as a browser request that went away. */
  signal?: AbortSignal;
  timeoutMs?: number;
  /** Sent as X-Request-ID; one is generated when absent. */
  requestId?: string;
}

function withoutTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

/** Stops a call at the caller's abort or at the timeout, whichever comes first. */
function callSignal(signal: AbortSignal | undefined, timeoutMs: number): AbortSignal {
  const timeout = AbortSignal.timeout(timeoutMs);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

/** The API's problem (RFC 9457) as an ApiError; any other reply keeps only its status. */
export async function readApiError(response: Response, requestId?: string): Promise<ApiError> {
  const problem: { code?: unknown; detail?: unknown } | undefined = response.headers
    .get("Content-Type")
    ?.includes("json")
    ? await response.json().catch(() => undefined)
    : undefined;
  const retryAfter = response.headers.get("Retry-After") ?? "";
  return new ApiError(
    response.status,
    typeof problem?.code === "string" ? problem.code : UNEXPECTED,
    typeof problem?.detail === "string" ? problem.detail : `HTTP ${response.status}`,
    /^\d+$/.test(retryAfter) ? Number(retryAfter) : undefined,
    response.headers.get("X-Request-ID") ?? requestId,
  );
}

/** REST client that sends the key and an X-Request-ID on every call; see `callSignal`. */
export function createApiClient(baseUrl: string, apiKey: string, timeoutMs = TIMEOUT_MS) {
  return createClient<paths>({
    baseUrl: withoutTrailingSlash(baseUrl),
    headers: { "X-API-Key": apiKey },
    fetch: async (request) => {
      if (!request.headers.has("X-Request-ID")) {
        request.headers.set("X-Request-ID", crypto.randomUUID());
      }
      const response = await fetch(request, { signal: callSignal(request.signal, timeoutMs) });
      // Thrown here, because openapi-fetch reads an error reply's body before the caller can.
      if (!response.ok) {
        throw await readApiError(response, request.headers.get("X-Request-ID") ?? undefined);
      }
      return response;
    },
  });
}

/** Runs a generated GraphQL document; HTTP errors and GraphQL errors throw ApiError. */
export async function executeGraphql<TResult, TVariables>(
  baseUrl: string,
  apiKey: string,
  document: TypedDocumentString<TResult, TVariables>,
  variables: TVariables,
  { signal, timeoutMs = TIMEOUT_MS, requestId = crypto.randomUUID() }: CallOptions = {},
): Promise<TResult> {
  const response = await fetch(`${withoutTrailingSlash(baseUrl)}/graphql`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey, "X-Request-ID": requestId },
    body: JSON.stringify({ query: document.toString(), variables }),
    signal: callSignal(signal, timeoutMs),
  });
  if (!response.ok) throw await readApiError(response, requestId);
  const replyId = response.headers.get("X-Request-ID") ?? requestId;
  const body = (await response.json().catch(() => null)) as {
    data?: TResult | null;
    errors?: { message: string; extensions?: { code?: unknown } }[];
  } | null;
  if (body?.errors?.length) {
    const code = body.errors[0].extensions?.code;
    throw new ApiError(
      response.status,
      typeof code === "string" ? code : UNEXPECTED,
      body.errors.map((error) => error.message).join("; "),
      undefined,
      replyId,
    );
  }
  // A body that is not JSON, or JSON without data, is no GraphQL reply (a proxy's page, say).
  if (body?.data == null) {
    throw new ApiError(response.status, UNEXPECTED, `HTTP ${response.status}`, undefined, replyId);
  }
  return body.data;
}

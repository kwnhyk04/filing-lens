// Typed FilingLens clients: REST through openapi-fetch, GraphQL through the generated documents.
// Server-side only: the API key must never reach a browser.
import createClient from "openapi-fetch";

import type { TypedDocumentString } from "./graphql/graphql";
import type { paths } from "./openapi";

export type { components, operations, paths } from "./openapi";
export * from "./graphql/graphql";

const TIMEOUT_MS = 30_000;

/** REST client that sends the key on every request and gives up after `timeoutMs`. */
export function createApiClient(baseUrl: string, apiKey: string, timeoutMs = TIMEOUT_MS) {
  return createClient<paths>({
    baseUrl,
    headers: { "X-API-Key": apiKey },
    fetch: (request) => fetch(request, { signal: AbortSignal.timeout(timeoutMs) }),
  });
}

/** Runs a generated GraphQL document; throws on HTTP errors and on GraphQL errors. */
export async function executeGraphql<TResult, TVariables>(
  baseUrl: string,
  apiKey: string,
  document: TypedDocumentString<TResult, TVariables>,
  variables: TVariables,
  timeoutMs = TIMEOUT_MS,
): Promise<TResult> {
  const response = await fetch(`${baseUrl}/graphql`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
    body: JSON.stringify({ query: document.toString(), variables }),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!response.ok) throw new Error(`GraphQL request failed with HTTP ${response.status}`);
  const body = (await response.json()) as { data?: TResult; errors?: { message: string }[] };
  if (body.errors?.length) throw new Error(body.errors.map((error) => error.message).join("; "));
  return body.data as TResult;
}

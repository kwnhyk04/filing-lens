// Sorts a failed API call: offline (show the demo), misconfigured (a rejected key) or a problem.
import { ApiError } from "../../clients/ts/index.ts";

export type Failure =
  | { kind: "offline" }
  | { kind: "misconfigured"; requestId?: string }
  | {
      kind: "problem";
      status: number;
      code: string;
      detail: string;
      retryAfterS?: number;
      requestId?: string;
    };

export function classify(error: unknown): Failure {
  if (!(error instanceof ApiError)) return { kind: "offline" }; // network error, timeout or abort
  const { status, code, message: detail, retryAfterS, requestId } = error;
  if (status === 401 || status === 403) return { kind: "misconfigured", requestId };
  // A database outage arrives as `internal` (a 500, or a GraphQL error on a 200), and a reply that
  // is no API problem, such as a proxy's 502 page, means the API is not there.
  if (code === "internal" || code === "unexpected_response") return { kind: "offline" };
  return { kind: "problem", status, code, detail, retryAfterS, requestId };
}

/** `api_call`'s failure label and log level: a browser that left is no warning. */
export function failureLabel(error: unknown, failure: Failure): { label: string; level: "info" | "warn" } {
  // The browser's own abort, or Next's `ResponseAborted` when the browser disconnects mid-request.
  const name = (error as { name?: unknown } | null)?.name;
  if (name === "AbortError" || name === "ResponseAborted") return { label: "client_aborted", level: "info" };
  return { label: failure.kind, level: "warn" };
}

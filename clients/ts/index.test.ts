// The client helpers under `node --test`. fetch is stubbed, so no server runs.
import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import {
  ApiError,
  CompaniesDocument,
  createApiClient,
  executeGraphql,
  readApiError,
} from "./index.ts";

const BASE = "http://api.test";
const KEY = "k".repeat(32);
const UUID = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

/** Stubs fetch with one reply and keeps every request sent. */
function reply(response: () => Response): Request[] {
  const sent: Request[] = [];
  globalThis.fetch = async (input, init) => {
    sent.push(new Request(input, init));
    return response();
  };
  return sent;
}

/** Stubs fetch with a call that ends only when its signal aborts, like a stalled server. */
function hang(): void {
  globalThis.fetch = (_input, init) =>
    new Promise((_resolve, reject) => {
      const signal = init?.signal;
      if (signal?.aborted) reject(signal.reason);
      signal?.addEventListener("abort", () => reject(signal.reason), { once: true });
    });
}

function problem(status: number, body: object, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify({ type: "about:blank", status, ...body }), {
    status,
    headers: { "Content-Type": "application/problem+json", ...headers },
  });
}

function fields(error: unknown) {
  assert.ok(error instanceof ApiError);
  assert.equal(error.name, "ApiError");
  const { status, code, message: detail, retryAfterS, requestId } = error;
  return { status, code, detail, retryAfterS, requestId };
}

const ERRORS: [string, () => Response, ReturnType<typeof fields>][] = [
  [
    "a problem with Retry-After and a request id",
    () =>
      problem(
        503,
        { title: "Service Unavailable", code: "ai_unavailable", detail: "Budget used up." },
        { "Retry-After": "120", "X-Request-ID": "req-1" },
      ),
    {
      status: 503,
      code: "ai_unavailable",
      detail: "Budget used up.",
      retryAfterS: 120,
      requestId: "req-1",
    },
  ],
  [
    "a 503 without Retry-After, as when AI is switched off",
    () => problem(503, { title: "Service Unavailable", code: "ai_unavailable", detail: "Off." }),
    {
      status: 503,
      code: "ai_unavailable",
      detail: "Off.",
      retryAfterS: undefined,
      requestId: undefined,
    },
  ],
  [
    "a problem without a detail",
    () => problem(500, { title: "Internal Server Error", code: "internal", detail: null }),
    {
      status: 500,
      code: "internal",
      detail: "HTTP 500",
      retryAfterS: undefined,
      requestId: undefined,
    },
  ],
  [
    "Retry-After as an HTTP date is left out",
    () =>
      problem(
        429,
        { title: "Too Many Requests", code: "rate_limited", detail: "Slow down." },
        { "Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT" },
      ),
    {
      status: 429,
      code: "rate_limited",
      detail: "Slow down.",
      retryAfterS: undefined,
      requestId: undefined,
    },
  ],
  [
    "a page from a proxy keeps only its status",
    () =>
      new Response("<html>Bad Gateway</html>", {
        status: 502,
        headers: { "Content-Type": "text/html" },
      }),
    {
      status: 502,
      code: "unexpected_response",
      detail: "HTTP 502",
      retryAfterS: undefined,
      requestId: undefined,
    },
  ],
  [
    "a problem type over a body that is not JSON",
    () =>
      new Response("upstream reset", {
        status: 500,
        headers: { "Content-Type": "application/problem+json" },
      }),
    {
      status: 500,
      code: "unexpected_response",
      detail: "HTTP 500",
      retryAfterS: undefined,
      requestId: undefined,
    },
  ],
];

for (const [name, response, expected] of ERRORS) {
  test(`readApiError: ${name}`, async () => {
    assert.deepEqual(fields(await readApiError(response())), expected);
  });
}

test("executeGraphql posts the query with the key and a fresh request id", async () => {
  const sent = reply(() => Response.json({ data: { companies: null } }));
  const data = await executeGraphql(`${BASE}/`, KEY, CompaniesDocument, { first: 2 });
  assert.deepEqual(data, { companies: null });
  const [request] = sent;
  assert.equal(request.url, `${BASE}/graphql`);
  assert.equal(request.method, "POST");
  assert.equal(request.headers.get("X-API-Key"), KEY);
  assert.match(request.headers.get("X-Request-ID") ?? "", UUID);
  assert.deepEqual(await request.json(), {
    query: CompaniesDocument.toString(),
    variables: { first: 2 },
  });
});

test("executeGraphql sends the caller's request id as it is", async () => {
  const sent = reply(() => Response.json({ data: {} }));
  await executeGraphql(BASE, KEY, CompaniesDocument, { first: 1 }, { requestId: "req-2" });
  assert.equal(sent[0].headers.get("X-Request-ID"), "req-2");
});

test("GraphQL errors throw an ApiError with the first error's code", async () => {
  const errors = [
    { message: "Unexpected error.", extensions: { code: "internal" } },
    { message: "Other.", extensions: { code: "invalid_input" } },
  ];
  reply(() => Response.json({ data: null, errors }, { headers: { "X-Request-ID": "req-3" } }));
  const error = await executeGraphql(BASE, KEY, CompaniesDocument, { first: 1 }).catch((e) => e);
  assert.deepEqual(fields(error), {
    status: 200,
    code: "internal",
    detail: "Unexpected error.; Other.",
    retryAfterS: undefined,
    requestId: "req-3",
  });
});

test("a GraphQL error without a code, such as a bad query, is an unexpected response", async () => {
  reply(() => Response.json({ data: null, errors: [{ message: "Cannot query field 'x'." }] }));
  const error = await executeGraphql(BASE, KEY, CompaniesDocument, { first: 1 }).catch((e) => e);
  assert.equal(fields(error).code, "unexpected_response");
});

test("an HTTP error on the GraphQL route keeps the request id sent", async () => {
  reply(() => new Response("Bad Gateway", { status: 502 }));
  const call = executeGraphql(BASE, KEY, CompaniesDocument, { first: 1 }, { requestId: "req-4" });
  assert.deepEqual(fields(await call.catch((e) => e)), {
    status: 502,
    code: "unexpected_response",
    detail: "HTTP 502",
    retryAfterS: undefined,
    requestId: "req-4",
  });
});

test("executeGraphql stops when the caller aborts, and at its timeout", { timeout: 5_000 }, async () => {
  hang();
  const caller = new AbortController();
  const options = { signal: caller.signal, timeoutMs: 60_000 };
  const call = executeGraphql(BASE, KEY, CompaniesDocument, { first: 1 }, options);
  caller.abort();
  await assert.rejects(call, { name: "AbortError" });
  const slow = executeGraphql(BASE, KEY, CompaniesDocument, { first: 1 }, { timeoutMs: 10 });
  await assert.rejects(slow, { name: "TimeoutError" });
});

test("the REST client stops when the caller aborts, and at its timeout", { timeout: 5_000 }, async () => {
  hang();
  const caller = new AbortController();
  const call = createApiClient(BASE, KEY, 60_000).GET("/v1/companies", { signal: caller.signal });
  caller.abort();
  await assert.rejects(call, { name: "AbortError" });
  await assert.rejects(createApiClient(BASE, KEY, 10).GET("/v1/companies"), { name: "TimeoutError" });
});

test("the REST client throws an error reply as an ApiError, keeping the request id sent", async () => {
  const api = createApiClient(BASE, KEY);
  reply(() =>
    problem(
      503,
      { title: "Service Unavailable", code: "ai_unavailable", detail: "Busy." },
      { "Retry-After": "30", "X-Request-ID": "req-6" },
    ),
  );
  assert.deepEqual(fields(await api.GET("/v1/companies").catch((e) => e)), {
    status: 503,
    code: "ai_unavailable",
    detail: "Busy.",
    retryAfterS: 30,
    requestId: "req-6",
  });
  reply(() => new Response("Bad Gateway", { status: 502 }));
  const call = api.GET("/v1/companies", { headers: { "X-Request-ID": "req-7" } });
  assert.deepEqual(fields(await call.catch((e) => e)), {
    status: 502,
    code: "unexpected_response",
    detail: "HTTP 502",
    retryAfterS: undefined,
    requestId: "req-7",
  });
});

test("the REST client sends the key and a request id, generated when absent", async () => {
  const sent = reply(() => Response.json({ items: [], next_cursor: null }));
  const api = createApiClient(`${BASE}//`, KEY);
  await api.GET("/v1/companies");
  await api.GET("/v1/companies", { headers: { "X-Request-ID": "req-5" } });
  assert.deepEqual(
    sent.map((request) => request.url),
    [`${BASE}/v1/companies`, `${BASE}/v1/companies`],
  );
  assert.equal(sent[0].headers.get("X-API-Key"), KEY);
  assert.match(sent[0].headers.get("X-Request-ID") ?? "", UUID);
  assert.equal(sent[1].headers.get("X-Request-ID"), "req-5");
});

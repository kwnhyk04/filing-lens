// The e2e stand-in for the FilingLens API: it checks X-API-Key and replays web/demo/snapshot.json.
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";

import type { components } from "../../clients/ts/index.ts";
import { API_KEY, MOCK, snapshot } from "./env.ts";

type Schemas = components["schemas"];
type AnswerEvent = Schemas["AnswerDelta"] | Schemas["AnswerCompleted"] | Schemas["AnswerFailed"];
type Answer = Schemas["Answer"];

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const cut = new Set<string>(); // questions whose stream the web closed before it finished
const cursor = (index: number) => Buffer.from(String(index)).toString("base64url");
const answerOf = (id: string) => snapshot.answers.find((item) => item.id === id)?.answer as Answer;

function problem(status: number, code: string, detail: string): Schemas["Problem"] {
  return { type: "about:blank", title: code, status, code, detail, errors: null };
}

function send(res: ServerResponse, status: number, body: object, headers: Record<string, string> = {}) {
  const type = status >= 400 ? "application/problem+json" : "application/json";
  res.writeHead(status, { "Content-Type": type, ...headers });
  res.end(JSON.stringify(body));
}

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(chunk as Buffer);
  return JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}") as Record<string, unknown>;
}

// Questions that take the error paths; other questions not in the snapshot get o02's refusal.
const ADMISSION: Record<string, [number, string, string, string?]> = {
  "e2e: rate limited": [429, "rate_limited", "At most 10 answers a minute.", "7"],
  "e2e: switched off": [503, "ai_unavailable", "AI is switched off on this server."],
  "e2e: busy": [503, "overloaded", "Too many answers in progress.", "2"],
};

/** c02 with its conclusion citing FilingLens's arithmetic on the two facts, as a calculation (K1). */
function calculated(): Answer {
  const c02 = answerOf("c02");
  const [alphabet, meta] = c02.citations;
  const quote =
    "Meta Platforms, Inc. (META): 200,966,000,000 USD. Alphabet Inc. (GOOGL): 402,836,000,000 USD." +
    " Alphabet Inc. (GOOGL) is higher by 201,870,000,000 USD, 100.45% more than Meta Platforms, Inc. (META).";
  const higher = "Alphabet's $402,836,000,000 was $201,870,000,000, or 100.45%, higher than Meta's $200,966,000,000 [1][2][3].";
  return {
    ...c02,
    answer: `${c02.answer.split(" Therefore")[0]} ${higher}`,
    citations: [alphabet, meta, { chunk_id: null, fact_id: null, calculation: { inputs: [1, 2] }, quote, filing_url: meta.filing_url }],
    checks: [
      ...c02.checks,
      { text: "$201,870,000,000", citation: 3, source_value: "201,870,000,000" },
      { text: "100.45%", citation: 3, source_value: "100.45" },
    ],
  };
}

/** What the API sends a key it does not know. */
function rejected(res: ServerResponse) {
  send(res, 401, problem(401, "unauthorized", "Missing or unknown API key."), { "WWW-Authenticate": "APIKey" });
}

async function stream(res: ServerResponse, question: string) {
  if (question === "e2e: rejected") return rejected(res);
  const admission = ADMISSION[question];
  if (admission) {
    const [status, code, detail, retryAfter] = admission;
    return send(res, status, problem(status, code, detail), retryAfter ? { "Retry-After": retryAfter } : {});
  }
  res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-store" });
  res.on("close", () => {
    if (!res.writableFinished) cut.add(question);
  });
  const emit = (event: AnswerEvent) => res.write(`data: ${JSON.stringify(event)}\n\n`);
  if (question === "e2e: failed") {
    emit({ type: "delta", text: "A draft that never finishes" });
    await sleep(200);
    emit({ type: "failed", problem: problem(502, "upstream_error", "No answer within 30 s.") });
    return res.end();
  }
  const rewritten = question === "e2e: rewritten"; // x02's answer carries validation warnings
  const slow = question.startsWith("e2e: slow"); // about 3 s of draft, so a test can leave mid-answer
  const recorded = snapshot.answers.find((item) => item.question === question)?.answer as Answer | undefined;
  const answer = rewritten ? answerOf("x02") : question === "e2e: calculated" ? calculated() : (recorded ?? answerOf("o02"));
  const draft = slow ? "Still drafting. ".repeat(50) : rewritten ? "A first draft that validation will rewrite." : answer.answer;
  for (const piece of draft.match(/[\s\S]{1,40}/g) ?? []) {
    emit({ type: "delta", text: piece });
    res.write(": ping\n\n");
    await sleep(150);
  }
  emit({ type: "completed", answer });
  res.end();
}

// The API's totals, counted from the snapshot: its companies, and the filings each lists.
const TOTALS = {
  companies: snapshot.companies.length,
  filings: snapshot.companies.reduce((sum, company) => sum + company.filings.edges.length, 0),
};

function graphql(res: ServerResponse, body: Record<string, unknown>) {
  const operation = /query\s+(\w+)/.exec(String(body.query))?.[1];
  const variables = (body.variables ?? {}) as Record<string, unknown>;
  // Cursors that act out a rejected key and an unexpected problem.
  if (variables.after === "e2e-rejected") return rejected(res);
  if (variables.after === "e2e-error") {
    const error = { message: "Too many requests.", extensions: { code: "rate_limited" } };
    return send(res, 200, { data: null, errors: [error] });
  }
  if (operation === "Totals") return send(res, 200, { data: { totals: TOTALS } });
  if (operation === "Companies" || operation === "Coverage") {
    const start = variables.after ? Number(Buffer.from(String(variables.after), "base64url").toString()) : 0;
    if (!Number.isInteger(start) || start < 0 || start > snapshot.companies.length) {
      const error = { message: "Not a cursor from this list.", extensions: { code: "invalid_input" } };
      return send(res, 200, { data: null, errors: [error] });
    }
    const page = snapshot.companies.slice(start, start + Number(variables.first ?? 20));
    const end = start + page.length;
    const edges = page.map((node, i) => ({ cursor: cursor(start + i + 1), node }));
    const pageInfo = { hasNextPage: end < snapshot.companies.length, endCursor: page.length ? cursor(end) : null };
    return send(res, 200, { data: { totals: TOTALS, companies: { edges, pageInfo } } });
  }
  if (operation === "Sources") {
    const pick = <T extends { id: string }>(items: T[], ids: unknown) =>
      (ids as string[]).flatMap((id) => items.filter((item) => item.id === id));
    const { chunks, facts } = snapshot.sources;
    const data = { chunks: pick(chunks, variables.chunkIds), facts: pick(facts, variables.factIds) };
    return send(res, 200, { data });
  }
  send(res, 200, { data: null, errors: [{ message: `The mock has no ${operation} operation.` }] });
}

const server = createServer(async (req, res) => {
  res.setHeader("X-Request-ID", String(req.headers["x-request-id"] ?? "mock"));
  if (req.url === "/healthz") return send(res, 200, { status: "ok" });
  if (req.headers["x-api-key"] !== API_KEY) return rejected(res);
  const url = new URL(req.url ?? "/", MOCK);
  if (req.method === "GET" && url.pathname === "/e2e/cut") {
    return send(res, 200, { cut: cut.has(url.searchParams.get("question") ?? "") });
  }
  const body = await readJson(req);
  if (req.method === "POST" && req.url === "/graphql") return graphql(res, body);
  if (req.method === "POST" && req.url === "/v1/answers/stream") return stream(res, String(body.question ?? ""));
  send(res, 404, problem(404, "not_found", "The mock has no such route."));
});

const { hostname, port } = new URL(MOCK);
server.listen(Number(port), hostname);

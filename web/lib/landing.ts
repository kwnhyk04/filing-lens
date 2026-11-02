// The landing page's results table, from the official eval report's Markdown: the report's own target,
// result and pass or fail for each row, in the page's words and units.

type Unit = "share" | "ms" | "usd";

// Each row's label in the report, its label here, its unit, and whether its target is a ceiling.
const ROWS: { report: string; label: string; unit: Unit; ceiling?: true }[] = [
  { report: "Numeric exact match (0.5%)", label: "Numeric accuracy (exact match)", unit: "share" },
  { report: "Citation coverage (last reply before removal)", label: "Citation coverage", unit: "share" },
  { report: "Citation precision (judge)", label: "Citation precision", unit: "share" },
  { report: "Faithfulness (judge)", label: "Faithfulness", unit: "share" },
  { report: "Correct refusal", label: "Correct refusals, unanswerable questions", unit: "share" },
  { report: "False refusal", label: "False refusals, answerable questions", unit: "share", ceiling: true },
  { report: "Time to first token p50", label: "Time to first token, p50", unit: "ms", ceiling: true },
  { report: "Full answer p95", label: "Full answer latency, p95", unit: "ms", ceiling: true },
  { report: "Retrieval recall@10", label: "Retrieval recall@10", unit: "share" },
  { report: "Cost per query, paid-equivalent", label: "Cost per query at paid rates", unit: "usd", ceiling: true },
];

export interface ResultRow {
  label: string;
  target: string;
  result: string;
  status: "Met" | "Below target" | "Not measured";
}

const percent = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });
const seconds = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

/** A report cell ("0.944", "1,546 ms", "$0.0010") as the page shows it ("94.4%", "1.55 s", "$0.0010"). */
function shown(cell: string, unit: Unit): string {
  const value = Number(cell.replace(/[$,]|\s*ms$/g, ""));
  if (Number.isNaN(value)) throw new Error(`Not a number in the eval report: "${cell}"`);
  if (unit === "ms") return `${seconds.format(value / 1000)} s`;
  if (unit === "usd") return `$${value.toFixed(4)}`;
  return percent.format(value);
}

/** The page's rows, each from the report's row of the same metric; a missing row fails the build. */
export function resultRows(markdown: string): ResultRow[] {
  const table = new Map<string, string[]>();
  for (const line of markdown.split("\n")) {
    const [label, ...cells] = line.split("|").slice(1, -1).map((cell) => cell.trim());
    // The first table with the label: a Claude-first report repeats it in its side-by-side table.
    if (cells.length && !table.has(label)) table.set(label, cells);
  }
  return ROWS.map(({ report, label, unit, ceiling }): ResultRow => {
    const cells = table.get(report);
    if (!cells) throw new Error(`The eval report has no "${report}" row`);
    const [target, measured, , , status] = cells;
    return {
      label,
      target: `${ceiling ? "≤ " : ""}${shown(target, unit)}`,
      result: shown(measured, unit),
      status: status === "pass" ? "Met" : status === "fail" ? "Below target" : "Not measured",
    };
  });
}

/** One run's result in a row of the comparison. */
export interface RunCell {
  result: string;
  status: ResultRow["status"];
}

/** A metric's row in the comparison: its target, then each official run's result. */
export interface ComparisonRow {
  label: string;
  target: string;
  claude: RunCell;
  free: RunCell;
}

/** The two official runs side by side, each from its own report; runs held to different targets fail the build. */
export function comparisonRows(claudeMarkdown: string, freeMarkdown: string): ComparisonRow[] {
  const free = resultRows(freeMarkdown);
  return resultRows(claudeMarkdown).map((row, i): ComparisonRow => {
    const other = free[i];
    if (other.target !== row.target) throw new Error(`The runs' targets differ for "${row.label}": ${row.target}, ${other.target}`);
    return {
      label: row.label,
      target: row.target,
      claude: { result: row.result, status: row.status },
      free: { result: other.result, status: other.status },
    };
  });
}

// The models the official runs measured, by name; a run with another fails the build until it is named here.
const MODELS: Record<string, string> = {
  "anthropic:claude-haiku-5-5": "Claude Haiku 5.5",
  "gemini:gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
  "groq:openai/gpt-oss-20b": "gpt-oss-20b on Groq",
};

/** "Claude Haiku 5.5": a run's `provider:model` by its name. */
export function modelName(id: string): string {
  const name = MODELS[id];
  if (!name) throw new Error(`No name for the measured model "${id}"`);
  return name;
}

export const REPO = "https://github.com/kwnhyk04/filing-lens";
export const sourceLink = (path: string) => `${REPO}/blob/main/${path}`;

/** The Architecture section's claims, each with what it means and the files that prove it; a unit test checks
    every path is in the repository. */
export const EVIDENCE: { claim: string; line: string; paths: string[] }[] = [
  {
    claim: "Rate-limited SEC ingestion",
    line: "Every worker shares one rate limiter in Redis that keeps under SEC's request limit, with retries and dead-letter queues.",
    paths: [
      "packages/core/src/filinglens_core/ratelimit.py",
      "packages/sec_client/src/filinglens_sec_client/__init__.py",
      "services/ingest/src/filinglens_ingest/replay.py",
    ],
  },
  {
    claim: "Hybrid retrieval",
    line: "PostgreSQL full-text search and pgvector similarity, fused by reciprocal rank, then reranked by a cross-encoder on the CPU.",
    paths: ["packages/retrieval/src/filinglens_retrieval/__init__.py", "packages/llm/src/filinglens_llm/local.py"],
  },
  {
    claim: "Grounded generation",
    line: "Quotes must match the passage word for word, and amounts the fact or passage they cite. Unsupported sentences are removed.",
    paths: ["packages/llm/src/filinglens_llm/validate.py", "services/api/src/filinglens_api/answering.py"],
  },
  {
    claim: "Reproducible evaluation",
    line: "A frozen test set, a calibrated judge, and reports fingerprinted with the exact code and prompt versions they measured.",
    paths: ["evals/golden/v2/manifest.json", "evals/judge.py", "evals/harness.py"],
  },
  {
    claim: "Quality gates in CI",
    line: "Pull requests that change the answer pipeline rerun the retrieval and answer evals against floors. A provider's quota stop fails the check instead of passing silently.",
    paths: [".github/workflows/ci.yml", "evals/thresholds.json"],
  },
  {
    claim: "End-to-end tracing",
    line: "One OpenTelemetry trace per question, with a span for each stage: routing, facts, search and generation.",
    paths: ["packages/telemetry/src/filinglens_telemetry/otel.py", "services/api/src/filinglens_api/answering.py"],
  },
];

const day = new Intl.DateTimeFormat("en-US", { dateStyle: "long", timeZone: "UTC" });

/** "October 17, 2026": a report's `created_at` as its UTC day. */
export const evalDate = (iso: string) => day.format(new Date(iso));

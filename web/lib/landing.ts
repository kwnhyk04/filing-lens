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

const day = new Intl.DateTimeFormat("en-US", { dateStyle: "long", timeZone: "UTC" });

/** "October 17, 2026": a report's `created_at` as its UTC day. */
export const evalDate = (iso: string) => day.format(new Date(iso));

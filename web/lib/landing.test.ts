// The landing page's figures under `node --test`: the eval report's table as the page shows it.
import assert from "node:assert/strict";
import { test } from "node:test";

import { evalDate, resultRows } from "./landing.ts";

// Rows as the harness writes them, CRLF included; the order differs from the page's on purpose.
const TABLE = [
  "# Eval: all, test, full",
  "",
  "| Metric | Target | Measured | 95% CI | n | Status |",
  "| --- | --- | --- | --- | --- | --- |",
  "| Retrieval recall@10 | 0.900 | 0.583 | 0.314 to 0.816 | 6 | fail |",
  "| MRR@10 | 0.700 | 0.833 | 0.500 to 1.000 | 6 | pass |",
  "| Numeric exact match (0.5%) | 0.920 | 1.000 | 1.000 to 1.000 | 12 | pass |",
  "| Citation precision (judge) | 0.950 | 0.944 | 0.833 to 1.000 | 20 | fail |",
  "| Citation coverage (last reply before removal) | 0.950 | 0.971 | 0.914 to 1.000 | 20 | pass |",
  "| Faithfulness (judge) | 0.920 | 0.970 | 0.906 to 1.000 | 20 | pass |",
  "| Correct refusal | 0.900 | 1.000 | 1.000 to 1.000 | 7 | pass |",
  "| False refusal | 0.050 | 0.130 | 0.000 to 0.261 | 23 | fail |",
  "| Time to first token p50 | 1,000 ms | 1,546 ms | 1,452 ms to 1,619 ms | 19 | fail |",
  "| Full answer p95 | 6,000 ms | 2,147 ms | 1,973 ms to 4,892 ms | 21 | pass |",
  "| Cost per query, paid-equivalent | $0.0150 | $0.0010 | $0.0006 to $0.0014 | 30 | pass |",
  "",
  "| Model | Calls | Live | Input tokens | Output tokens |",
  "| `groq:openai/gpt-oss-20b` | 30 | 29 | 30,931 | 2,264 |",
].join("\r\n");

test("the report's table, in the page's order, units and words", () => {
  assert.deepEqual(resultRows(TABLE), [
    { label: "Numeric accuracy (exact match)", target: "92%", result: "100%", status: "Met" },
    { label: "Citation coverage", target: "95%", result: "97.1%", status: "Met" },
    { label: "Citation precision", target: "95%", result: "94.4%", status: "Below target" },
    { label: "Faithfulness", target: "92%", result: "97%", status: "Met" },
    { label: "Correct refusals, unanswerable questions", target: "90%", result: "100%", status: "Met" },
    { label: "False refusals, answerable questions", target: "≤ 5%", result: "13%", status: "Below target" },
    { label: "Time to first token, p50", target: "≤ 1 s", result: "1.55 s", status: "Below target" },
    { label: "Full answer latency, p95", target: "≤ 6 s", result: "2.15 s", status: "Met" },
    { label: "Retrieval recall@10", target: "90%", result: "58.3%", status: "Below target" },
    { label: "Cost per query at paid rates", target: "≤ $0.0150", result: "$0.0010", status: "Met" },
  ]);
});

test("a metric the report could not measure says so", () => {
  const uncalibrated = TABLE.replace("| 20 | fail |", "| 20 | not measured: judge not calibrated |");
  const row = resultRows(uncalibrated).find((r) => r.label === "Citation precision");
  assert.equal(row?.status, "Not measured");
});

test("a report without one of the page's rows fails, naming the row", () => {
  const without = TABLE.replace(/\| False refusal \|[^\r\n]*/, "");
  assert.throws(() => resultRows(without), /False refusal/);
});

test("the run's date is its UTC day, wherever the build runs", () => {
  assert.equal(evalDate("2026-10-17T07:24:00+00:00"), "October 17, 2026");
  assert.equal(evalDate("2026-10-17T23:59:00+00:00"), "October 17, 2026");
  assert.equal(evalDate("2026-10-17T00:30:00+02:00"), "October 16, 2026");
});

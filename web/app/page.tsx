// The public landing page: no session and no API call. Its figures come from the official eval report and
// the demo snapshot, imported at build time; e2e/landing.spec.ts fails when the page and they drift apart.
import "./landing.css";

import { cookies } from "next/headers";

import claude from "../../evals/reports/2026-10-31-claude-first.json";
import claudeTable from "../../evals/reports/2026-10-31-claude-first.md";
import report from "../../evals/reports/2026-10-31.json";
import table from "../../evals/reports/2026-10-31.md";
import { Hero } from "../components/hero.tsx";
import { LandingHeader } from "../components/landing-header.tsx";
import { Overview } from "../components/overview.tsx";
import { demo } from "../lib/demo.ts";
import { evalDate, type ResultRow, resultRows } from "../lib/landing.ts";
import { heroStory } from "../lib/story.ts";
import { THEME_COOKIE, themeOf } from "../lib/theme.ts";

// The two official runs of golden v2's test split: Claude first, as the live site runs while its credits
// last, and the free models alone, which CI's floors come from.
const RUNS = [
  { id: "claude-first", title: "Claude first: the live site while its credits last", run: claude, table: claudeTable },
  { id: "free", title: "Free models only: CI's floors, and the live site once the credits end", run: report, table },
].map((item) => ({ ...item, rows: resultRows(item.table) }));
const { config, judge_calibration: judge } = report;
const labeler = judge.labeler.charAt(0).toUpperCase() + judge.labeler.slice(1);
const story = heroStory(demo);

const STACK = [
  "Python",
  "FastAPI",
  "Strawberry GraphQL",
  "Celery",
  "RabbitMQ",
  "Redis",
  "PostgreSQL",
  "pgvector",
  "SQLAlchemy",
  "Next.js",
  "OpenTelemetry",
  "Claude",
  "Gemini",
  "Groq",
];

// How an answer is made, laid out after FreightAudit's How it works (the same owner's project): each step's icon,
// from Lucide (ISC licence, docs/third-party.md: route, search, message-square-text, shield-check), a title, one
// line and its points. The two figures come from the official report, as the page's others do.
const STEPS = [
  {
    title: "Route",
    icon: (
      <>
        <circle cx="6" cy="19" r="3" />
        <path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15" />
        <circle cx="18" cy="5" r="3" />
      </>
    ),
    line: "A small model reads the question.",
    points: ["Which company, which years, which figure or topic.", "Whether the filings can answer it at all."],
  },
  {
    title: "Retrieve",
    icon: (
      <>
        <path d="m21 21-4.34-4.34" />
        <circle cx="11" cy="11" r="8" />
      </>
    ),
    line: "Figures come from XBRL facts first; the rest from the filings' passages.",
    points: [
      `A keyword and meaning search over ${report.index.chunks.toLocaleString("en-US")} passages.`,
      `A reranker picks the best of the top ${config.rerank_candidates}.`,
    ],
  },
  {
    title: "Answer",
    icon: (
      <>
        <path d="M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z" />
        <path d="M7 11h10" />
        <path d="M7 15h6" />
        <path d="M7 7h8" />
      </>
    ),
    line: "The answer streams in as a draft, not yet checked.",
    points: ["Each sentence cites a numbered source.", "The checked answer then takes the draft's place."],
  },
  {
    title: "Check",
    icon: (
      <>
        <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
        <path d="m9 12 2 2 4-4" />
      </>
    ),
    line: "Every quote and amount is checked against its source.",
    points: [
      "Quotes must match their passage word for word.",
      "A failing draft is redone once; sentences that still fail are removed.",
      "With none left, the answer is a refusal, not a guess.",
    ],
  },
];

/** One run's results: each metric's target, its result, and whether it met the target. */
function ResultsTable({ caption, rows }: { caption: string; rows: ResultRow[] }) {
  return (
    <div className="scroll">
      <table>
        <caption className="visually-hidden">
          {caption}: each metric&apos;s target, its result, and whether it met the target
        </caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col" className="num">
              Target
            </th>
            <th scope="col" className="num">
              Result
            </th>
            <th scope="col">
              <span className="visually-hidden">Status</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              <td className="num">{row.target}</td>
              <td className="num measured">{row.result}</td>
              <td>
                <span className={row.status === "Met" ? "badge ok" : "badge warn"}>{row.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function LandingPage() {
  const theme = themeOf((await cookies()).get(THEME_COOKIE)?.value);
  return (
    <>
      <LandingHeader theme={theme} />
      <main id="main" className="landing">
        <Hero story={story} companies={demo.companies.length} answers={demo.answers.length} />
        <Overview />

        <section id="how" className="band" aria-labelledby="how-title">
          <h2 id="how-title">How an answer is made</h2>
          <ol className="how-steps">
            {STEPS.map((step, i) => (
              <li key={step.title}>
                <span className="step-number" aria-hidden="true">
                  {i + 1}
                </span>
                <span className="step-icon" aria-hidden="true">
                  <svg viewBox="0 0 24 24" focusable="false">
                    {step.icon}
                  </svg>
                </span>
                <h3>{step.title}</h3>
                <p className="step-line">{step.line}</p>
                <ul>
                  {step.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </section>

        <section id="results" aria-labelledby="results-title">
          <h2 id="results-title">Evaluation results</h2>
          <p>
            Measured on {report.records.answer.length} questions from golden set v2&apos;s test split on{" "}
            {evalDate(report.created_at)}, twice, judging by <code>{config.judge}</code>. Nothing was tuned on this
            set.
          </p>
          <p>
            On the live site, Claude Haiku 5.5 routes and answers first, within its daily budget and while its
            prepaid credits last; then the free models: Gemini 3.5 Flash-Lite answers, gpt-oss-20b on Groq routes,
            and gpt-oss-20b on NVIDIA is the last fallback.
          </p>
          {RUNS.map(({ id, title, run, rows }) => (
            <div key={id} id={`results-${id}`}>
              <h3>{title}</h3>
              <p className="small">
                Answers by <code>{run.config.primary}</code> (thinking {run.config.thinking}), routing by{" "}
                <code>{run.config.router}</code>.
              </p>
              <ResultsTable caption={title} rows={rows} />
            </div>
          ))}
          <p className="small">
            Citation precision and faithfulness are graded by an LLM judge, <code>{config.judge}</code>, calibrated
            against labels written by {labeler} (Cohen&apos;s kappa {judge.kappa.toFixed(2)}), not by a human.
            Retrieval recall rests on {report.metrics.retrieval["recall@10"].n} questions, whose passage labels are
            AI-labeled, cross-checked blind by a second model; no human spot check in v2.
          </p>
        </section>

        <section id="architecture" className="band" aria-labelledby="architecture-title">
          <h2 id="architecture-title">Architecture</h2>
          <div className="features">
            <div>
              <h3>Rate-limited SEC ingestion</h3>
              <p>
                Every worker shares one rate limiter in Redis that keeps under SEC&apos;s request limit, with
                retries and dead-letter queues.
              </p>
            </div>
            <div>
              <h3>Hybrid retrieval</h3>
              <p>
                PostgreSQL full-text search and pgvector similarity, fused by reciprocal rank, then reranked by a
                cross-encoder on the CPU.
              </p>
            </div>
            <div>
              <h3>Grounded generation</h3>
              <p>
                Quotes must match the passage word for word, and amounts the fact or passage they cite. Unsupported
                sentences are removed.
              </p>
            </div>
            <div>
              <h3>Reproducible evaluation</h3>
              <p>
                A frozen test set, a calibrated judge, and reports fingerprinted with the exact code and prompt
                versions they measured.
              </p>
            </div>
            <div>
              <h3>Quality gates in CI</h3>
              <p>
                Pull requests that change the answer pipeline rerun the retrieval and answer evals against floors. A
                provider&apos;s quota stop fails the check instead of passing silently.
              </p>
            </div>
            <div>
              <h3>End-to-end tracing</h3>
              <p>
                One OpenTelemetry trace per question, with a span for each stage: routing, facts, search and
                generation.
              </p>
            </div>
          </div>
          <ul className="chips" aria-label="Stack">
            {STACK.map((name) => (
              <li key={name}>{name}</li>
            ))}
          </ul>
        </section>
      </main>
    </>
  );
}

// The public landing page: no API call, and the session cookie only to offer Ask or Sign in. Its figures come
// from the official eval reports and the demo snapshot, imported at build time; e2e/landing.spec.ts fails when
// the page and they drift apart.
import "./landing.css";

import { cookies } from "next/headers";

import report from "../../evals/reports/2026-11-06.json";
import table from "../../evals/reports/2026-11-06.md";
import claude from "../../evals/reports/2026-11-06-claude-first.json";
import claudeTable from "../../evals/reports/2026-11-06-claude-first.md";
import devHaiku from "../../evals/reports/runs/20261103T175043Z-answer-dev-full-claude-first.json";
import devSonnetOff from "../../evals/reports/runs/20261103T175921Z-answer-dev-full-claude-first.json";
import devSonnetAdaptive from "../../evals/reports/runs/20261104T000849Z-answer-dev-full-claude-first.json";
import { Hero } from "../components/hero.tsx";
import { LandingHeader } from "../components/landing-header.tsx";
import { Overview } from "../components/overview.tsx";
import { demo } from "../lib/demo.ts";
import { comparisonRows, EVIDENCE, evalDate, modelName, type RunCell, sourceLink } from "../lib/landing.ts";
import { hasSession } from "../lib/server.ts";
import { heroStory } from "../lib/story.ts";
import { THEME_COOKIE, themeOf } from "../lib/theme.ts";

// The two official runs of golden v3's test split, side by side: Claude first, as the live site runs while its
// credits last, and the free models alone, which CI's floors come from.
const ROWS = comparisonRows(claudeTable, table);
const RUNS = [
  { key: "claude", name: "Claude first", run: claude, report: "evals/reports/2026-11-06-claude-first.md" },
  { key: "free", name: "Free models only", run: report, report: "evals/reports/2026-11-06.md" },
] as const;
const { config, judge_calibration: judge } = report;
const labeler = judge.labeler.charAt(0).toUpperCase() + judge.labeler.slice(1);
const story = heroStory(demo);
type DevRun = { metrics: { answer: { citation_precision: { value: number }; cost_usd: { value: number } } } };
const precision = (run: DevRun) => run.metrics.answer.citation_precision.value.toFixed(3);
const costPerQuery = (run: DevRun) => `$${run.metrics.answer.cost_usd.value.toFixed(4)}`;

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
    line: "The model drafts the answer, not yet checked.",
    points: ["Each sentence cites a numbered source.", "Only the checked answer is shown."],
  },
  {
    title: "Check",
    icon: (
      <>
        <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
        <path d="m9 12 2 2 4-4" />
      </>
    ),
    line: "Quotes and the amounts code can read are checked against their sources.",
    points: [
      "Quotes must match their passage word for word.",
      "Dollar amounts, percentages and comma-grouped numbers must match a cited source in scale, sign and unit. Which line item and period a figure belongs to is not checked.",
      "A failing draft is redone once; sentences that still fail are removed, and with none left the answer is a refusal, not a guess.",
    ],
  },
];

/** One run's result: its figure in bold with its badge, which wraps under it in a narrow column. On a phone's card
    its label names the run, its model and date, as the column's head does on a desktop; the date keeps to one line,
    so a narrow card breaks the label after the model. */
function Result({ cell, run, date }: { cell: RunCell; run: string; date: string }) {
  return (
    <td>
      <span className="cell-label">
        {run}, <span className="date">{date}</span>
      </span>
      <span className="result">
        <strong className="measured">{cell.result}</strong>{" "}
        <span className={cell.status === "Met" ? "badge ok" : "badge warn"}>{cell.status}</span>
      </span>{" "}
      <span className="run-meta">{cell.detail}</span>
    </td>
  );
}

/** Both official runs, after FreightAudit's landing: each metric's target, then each run's result, each run named
    in its column's head by its answer model and date. Below 40rem each row is a card (app/landing.css). */
function ResultsTable() {
  return (
    <div className="scroll" role="region" aria-label="Results by metric" tabIndex={0}>
      <table className="compare">
        <caption className="visually-hidden">
          Each metric&apos;s target, then each run&apos;s result and whether it met the target
        </caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            <th scope="col" className="num">
              Target
            </th>
            {RUNS.map(({ key, name, run }) => (
              <th key={key} scope="col">
                {name}
                <span className="run-meta">
                  {modelName(run.config.primary)} · {evalDate(run.created_at)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row) => (
            <tr key={row.label}>
              <th scope="row">{row.label}</th>
              <td className="num">
                <span className="cell-label">Target</span>
                {row.target}
              </td>
              {RUNS.map(({ key, name, run }) => (
                <Result key={key} cell={row[key]} run={`${name}, ${modelName(run.config.primary)}`} date={evalDate(run.created_at)} />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Props = { searchParams: Promise<Record<string, string | string[] | undefined>> };

export default async function LandingPage({ searchParams }: Props) {
  const theme = themeOf((await cookies()).get(THEME_COOKIE)?.value);
  const signedIn = await hasSession();
  // Sign-out lands here with ?signed-out=1; an old link to it tells someone signed in nothing.
  const signedOut = !signedIn && (await searchParams)["signed-out"] === "1";
  return (
    <>
      <LandingHeader theme={theme} signedIn={signedIn} />
      <main id="main" className="landing">
        <Hero
          story={story}
          companies={demo.companies.length}
          answers={demo.answers.length}
          notice={signedOut ? "You're signed out. Thanks for stopping by." : undefined}
        />
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
            Golden set v3&apos;s test split on <code>corpus-v3</code>, answered two ways. Claude first is how the live
            site answers while its credits last; the free models alone are what CI&apos;s floors come from, and what
            answers once the credits end. A row reads Met or Below target only where its whole 95% interval clears or
            misses the target; otherwise it reads Inconclusive.
          </p>
          <ResultsTable />
          <div className="results-notes">
            <p className="small" data-testid="measured-on">
              Measured on {report.records.answer.length} questions and {report.index.chunks.toLocaleString("en-US")}{" "}
              passages: Claude first on {evalDate(claude.created_at)}, the free models on {evalDate(report.created_at)}.
              Production has served the same corpus since the parser fix of November 6, 2026, which restored digits in
              table cells. In the free models&apos; run, Gemini&apos;s first token came slowly in bursts, which drives that
              column&apos;s latency; the cause is not confirmed.
              {claude.prompts.answer_system !== report.prompts.answer_system &&
                " The free models' run also predates the answer prompt Claude first used."}
            </p>
            <p className="small" data-testid="gold-note">
              No prompt was tuned on this set, but its answers were read by hand on November 5, 2026, before the amount
              check changed, so treat it as seen. Numeric gold comes from the same XBRL lookup the answers use, so exact
              match shows the model repeats the figure it was given, not that the lookup is right. Claude labeled the
              passages, its labels calibrated the judge, and Claude wrote the Claude-first answers; no human checked
              golden v3.
            </p>
            <p className="small">
              {RUNS.map(({ key, name, run }) => (
                <span key={key}>
                  {name}: answers by <code>{run.config.primary}</code> (thinking {run.config.thinking}), routing by{" "}
                  <code>{run.config.router}</code>.{" "}
                </span>
              ))}
            </p>
            <p className="small">
              On the live site, Claude Haiku 5.5 routes and answers first, within its daily budget and while its
              prepaid credits last; then the free models: Gemini 3.5 Flash-Lite answers, gpt-oss-20b on Groq routes,
              and gpt-oss-20b on NVIDIA is the last fallback.
            </p>
            <p className="small" data-testid="sonnet-note">
              Claude Sonnet 5.5 was measured too, on the {devHaiku.records.answer.length} dev questions, not this test
              set: citation precision {precision(devSonnetOff)} with thinking off and {precision(devSonnetAdaptive)} with
              adaptive thinking against Haiku&apos;s {precision(devHaiku)}, at {costPerQuery(devSonnetOff)} and{" "}
              {costPerQuery(devSonnetAdaptive)} a query against {costPerQuery(devHaiku)}. Haiku stayed; see{" "}
              <a href={sourceLink("evals/README.md")}>the measured decision</a>.
            </p>
            <p className="small">
              Citation precision and faithfulness are graded by an LLM judge, <code>{config.judge}</code>, calibrated
              against labels written by {labeler} (Cohen&apos;s kappa {judge.kappa.toFixed(2)}), not by a human.
            </p>
            <p className="small">
              Retrieval recall rests on {report.metrics.retrieval["recall@10"].n} questions, whose passage labels are
              golden v2&apos;s, moved to the re-parsed passages by exact text or word overlap: AI-labeled, cross-checked
              blind by a second model; no human spot check in v2. Some gold passages wait for a person and stay out of
              the score, so recall does not compare with golden v2&apos;s.
            </p>
            <p className="small">
              Complete results with 95% confidence intervals are in the reports:{" "}
              <a href={sourceLink(RUNS[0].report)}>Claude first</a> and <a href={sourceLink(RUNS[1].report)}>free models only</a>.
            </p>
          </div>
        </section>

        {/* After FreightAudit's "Engineering, with its evidence": each claim, what it means, and its proof. */}
        <section id="architecture" className="band" aria-labelledby="architecture-title">
          <h2 id="architecture-title">Architecture</h2>
          <p>Each claim links to the files that prove it.</p>
          <dl className="evidence">
            {EVIDENCE.map(({ claim, line, paths }) => (
              <div key={claim}>
                <dt>{claim}</dt>
                <dd>
                  <p>{line}</p>
                  <p className="evidence-links">
                    {paths.map((path) => (
                      <a key={path} href={sourceLink(path)}>
                        <code>{path}</code>
                      </a>
                    ))}
                  </p>
                </dd>
              </div>
            ))}
          </dl>
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

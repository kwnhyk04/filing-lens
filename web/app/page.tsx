// The public landing page: no session and no API call. Its figures come from the official eval report and
// the demo snapshot, imported at build time; e2e/landing.spec.ts fails when the page and they drift apart.
import Link from "next/link";

import claude from "../../evals/reports/2026-10-31-claude-first.json";
import claudeTable from "../../evals/reports/2026-10-31-claude-first.md";
import report from "../../evals/reports/2026-10-31.json";
import table from "../../evals/reports/2026-10-31.md";
import { AnswerText, sourceLabel } from "../components/answer-view.tsx";
import { LandingHeader } from "../components/chrome.tsx";
import { demo } from "../lib/demo.ts";
import { evalDate, type ResultRow, resultRows, SAMPLE } from "../lib/landing.ts";

// The two official runs of golden v2's test split: Claude first, as the live site runs while its credits
// last, and the free models alone, which CI's floors come from.
const RUNS = [
  { id: "claude-first", title: "Claude first: the live site while its credits last", run: claude, table: claudeTable },
  { id: "free", title: "Free models only: CI's floors, and the live site once the credits end", run: report, table },
].map((item) => ({ ...item, rows: resultRows(item.table) }));
const { config, judge_calibration: judge } = report;
const labeler = judge.labeler.charAt(0).toUpperCase() + judge.labeler.slice(1);
const sample = demo.answers.find((item) => item.id === SAMPLE);
if (!sample) throw new Error(`The demo snapshot has no answer ${SAMPLE}`);
const { question, answer } = sample;
const citation = answer.citations[0];

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

/** The hero's saved answer, its first source, and what the check made sure of. */
function Sample() {
  return (
    <figure className="sample">
      <p className="sample-question">{question}</p>
      <AnswerText answer={answer} sources={demo.sources} prefix="sample-" />
      <div className="sample-source" id="sample-source-1">
        <p className="sample-name">1 · {sourceLabel(citation, demo.sources)}</p>
        <p className="sample-quote">{citation.quote}</p>
        <p className="sample-check">
          {citation.fact_id
            ? "Checked: the amount matches this XBRL fact"
            : "Checked: the quote is in the filing, word for word"}
        </p>
      </div>
      <figcaption>A saved answer from golden v1&apos;s test run, as the demo shows it.</figcaption>
    </figure>
  );
}

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
                <span className={row.status === "Met" ? "pill" : "tag"}>{row.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      <LandingHeader />
      <main id="main" className="landing">
        <section className="hero" aria-labelledby="hero-title">
          <div className="hero-text">
            <p className="eyebrow">Questions on SEC filings</p>
            <h1 id="hero-title">Ask a company&apos;s annual report. Get an answer you can check.</h1>
            <p className="lead">
              FilingLens answers questions about {demo.companies.length} companies&apos; 10-K filings. Every
              sentence cites a passage or an XBRL fact from the filing, every amount must match the source it
              cites, and when the filings don&apos;t say, it tells you so.
            </p>
            <p className="cta">
              {/* A plain link: signed out, the sign-in gate sends it to sign-in first, then back to Ask. */}
              <a href="/ask" className="button">
                Try the live demo
              </a>
              <Link href="/demo" className="button quiet">
                Read sample answers, no sign-in
              </Link>
            </p>
            <p className="small">
              When the live backend is offline, the site serves {demo.answers.length} saved sample answers.
            </p>
          </div>
          <Sample />
        </section>

        <section id="how" className="band" aria-labelledby="how-title">
          <h2 id="how-title">How an answer is made</h2>
          <ol className="steps">
            <li>
              <h3>01 Route</h3>
              <p>
                A small model reads the question: which company, which years, which figure or topic, and whether
                the filings can answer it at all.
              </p>
            </li>
            <li>
              <h3>02 Retrieve</h3>
              <p>
                Figures are looked up in the companies&apos; XBRL facts first. Everything else is a keyword and
                meaning search over {report.index.chunks.toLocaleString("en-US")} passages, then a reranker picks
                the best from the top {config.rerank_candidates}.
              </p>
            </li>
            <li>
              <h3>03 Answer</h3>
              <p>
                The answer streams in as a draft, marked as not yet checked, with numbered sources. The checked
                answer then takes its place.
              </p>
            </li>
            <li>
              <h3>04 Check</h3>
              <p>
                Quotes must match their passage word for word, and amounts the fact or passage they cite. A failing
                draft is redone once; sentences that still fail are removed, and with none left the answer is a
                refusal, not a guess.
              </p>
            </li>
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

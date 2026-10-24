// The public landing page: no session and no API call. Its figures come from the official eval report and
// the demo snapshot, imported at build time; e2e/landing.spec.ts fails when the page and they drift apart.
import Link from "next/link";

import report from "../../evals/reports/2026-10-17.json";
import table from "../../evals/reports/2026-10-17.md";
import { AnswerText, sourceLabel } from "../components/answer-view.tsx";
import { LandingHeader } from "../components/chrome.tsx";
import { demo } from "../lib/demo.ts";
import { evalDate, resultRows, SAMPLE } from "../lib/landing.ts";

const rows = resultRows(table);
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
      <figcaption>A saved answer from the evaluation&apos;s test run, as the demo shows it.</figcaption>
    </figure>
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
            Measured on {report.records.answer.length} questions from the golden set&apos;s test split on{" "}
            {evalDate(report.created_at)}, with free-tier models: answers by <code>{config.primary}</code> (thinking{" "}
            {config.thinking}), routing by <code>{config.router}</code>, judging by <code>{config.judge}</code>.
            Nothing was tuned on this set.
          </p>
          <p>
            On the live site, Claude Haiku 5.5 answers first, within its daily budget and while its prepaid credits
            last; then Gemini 3.5 Flash-Lite, then gpt-oss-20b on NVIDIA. The table measures the free models, not
            Claude.
          </p>
          <div className="scroll">
            <table>
              <caption className="visually-hidden">Each metric&apos;s target, its result, and whether it met the target</caption>
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
          <p className="small">
            Citation precision and faithfulness are graded by an LLM judge, <code>{config.judge}</code>, calibrated
            against labels written by {labeler} (Cohen&apos;s kappa {judge.kappa.toFixed(2)}), not by a human.
            Retrieval recall rests on {report.metrics.retrieval["recall@10"].n} questions, whose passage labels are
            AI-written and spot-checked by a non-expert, not verified by experts.
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

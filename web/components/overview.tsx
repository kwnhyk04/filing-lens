// The landing page's overview, after Hirael's feature-10 (MIT; docs/third-party.md): a serif head, then one
// sheet split by hairlines into a saved answer with its passage, two figures, the newest feature and the
// jobs every answer goes through. Its Tailwind and shadcn cards became FilingLens's CSS (app/landing.css).
import claude from "../../evals/reports/2026-11-06-claude-first.json";
import { demo } from "../lib/demo.ts";
import { heroStory, QUOTE } from "../lib/story.ts";
import { AnswerText } from "./answer-view.tsx";

const REPO = "https://github.com/kwnhyk04/filing-lens";
const saved = heroStory(demo, QUOTE);

// demo/snapshot.json: the indexed filings it lists, one per company, as the demo header's "30 filings".
const filings = demo.companies.reduce((sum, company) => sum + company.filings.edges.length, 0);
// evals/reports/2026-11-06-claude-first.json, metrics.answer.numeric_exact_match: the same 12 of 12 as the
// free-models run (2026-11-06.json); e2e/landing.spec.ts checks both.
const exact = claude.metrics.answer.numeric_exact_match;
const whole = (share: number) => `${Math.round(share * 100)}%`;

const FIGURES = [
  { label: "Filings indexed", value: String(filings), caption: "One 10-K from each company." },
  {
    label: "Exact numbers",
    value: whole(exact.value),
    caption: `${Math.round(exact.value * exact.n)} of ${exact.n} numeric test questions within 0.5% in both official runs (95% CI ${whole(exact.low)} to ${whole(exact.high)}), against gold from the same XBRL lookup the answers use.`,
  },
];

const JOBS = [
  ["Ask", "Ask in plain words about a company's 10-K."],
  ["Cite", "Every sentence cites a passage or an XBRL fact from the filing."],
  ["Check", "Quotes must match their passage word for word, and the amounts code can read a cited source in scale, sign and unit."],
];

export function Overview() {
  return (
    <section id="overview" className="overview" aria-labelledby="overview-title">
      <div className="overview-head">
        <h2 id="overview-title">At a glance.</h2>
        <p>A sourced answer, tested numbers, and the newest feature.</p>
      </div>

      <div className="overview-grid">
        <div className="overview-cell overview-quote">
          <p className="overview-label">A saved answer</p>
          <h3>{saved.question}</h3>
          <blockquote>
            <AnswerText answer={saved.answer} sources={saved.sources} prefix="overview-" />
          </blockquote>
          {saved.passages.map((passage) => (
            <p key={passage.n} id={`overview-source-${passage.n}`} className="overview-source" tabIndex={-1}>
              <span className="overview-n" aria-hidden="true">
                {passage.n}
              </span>
              <span>
                <cite>{passage.label}</cite>
                <span className="overview-label">From golden v1&apos;s test run</span>
              </span>
            </p>
          ))}
        </div>

        {FIGURES.map((figure) => (
          <div key={figure.label} className="overview-cell overview-figure">
            <p className="overview-label">{figure.label}</p>
            <p className="overview-value">{figure.value}</p>
            <p>{figure.caption}</p>
          </div>
        ))}

        <div className="overview-cell overview-work">
          <div className="overview-work-head">
            <div>
              <p className="overview-label">New in Ask</p>
              <h3>Recent questions</h3>
            </div>
            <a href={`${REPO}/pull/42`} className="button">
              Read the pull request
              {/* Lucide's arrow-right (ISC licence, docs/third-party.md). */}
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M5 12h14m-7-7 7 7-7 7" />
              </svg>
            </a>
          </div>
          <p>
            Your answered questions from this session wait under the answer, with their times. Pick one, or ask it
            again, and the stored answer comes back with its sources and checks.
          </p>
        </div>

        <div className="overview-cell overview-jobs">
          <h3 className="overview-label">What it does</h3>
          <dl>
            {JOBS.map(([title, body]) => (
              <div key={title}>
                <dt>{title}</dt>
                <dd>{body}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}

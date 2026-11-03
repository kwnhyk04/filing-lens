// The answer card, in the landing hero's look and order (docs/design.md): the question in a bubble, how the router
// read it, the numbered sources and the filings they come from, the reply's heading and its text with citations, the
// check, then the number checks, the notes and the foot. Ask shows "Reading the filings…" (`waiting`) until the
// checked answer and its sources are both in, then the parts one by one (`shown`), the text a sentence a part; a
// stored answer and the demo's saved ones show it whole and still. Renders on the server or the client.
import type { ReactNode } from "react";

import { checkLine, citedFilings, readingChips, sourceLabel, type Answer } from "../lib/answer.ts";
import type { Sources } from "../lib/demo.ts";
import { type Part, revealParts } from "../lib/stage.ts";
import { AnswerText, FigureChecks } from "./answer-view.tsx";
import { Glyph, GLYPHS } from "./story-panel.tsx";

type Heading = "h2" | "h3";

interface Parts {
  sources?: Sources;
  sourcesFailed?: boolean;
  /** Beside "Answer": what the browser timed, or when the answer was given earlier. */
  head?: ReactNode;
  /** Copy, Ask again and New question, on Ask. */
  actions?: ReactNode;
  prefix?: string;
}

interface Props extends Parts {
  question: string;
  /** The checked answer, once the stream completes it. */
  answer?: Answer | null;
  /** What went wrong, in place of the answer. */
  problem?: ReactNode;
  /** Under the question until the first part shows: Ask's "Reading the filings…". */
  waiting?: ReactNode;
  /** How many of the answer's parts show, in order: all of them unless Ask is revealing them. */
  shown?: number;
  /** The card clears before the next question's takes its place. */
  leaving?: boolean;
  /** A stored or saved answer, or no motion allowed: nothing moves in. */
  still?: boolean;
  level?: 2 | 3;
}

export function AnswerCard({ question, answer, problem, waiting, shown = Infinity, leaving, still, level, ...parts }: Props) {
  const heading: Heading = level === 3 ? "h3" : "h2";
  const order = answer ? revealParts(answer, parts.sources, Boolean(parts.sourcesFailed)) : [];
  const visible = problem ? 0 : Math.min(shown, order.length);
  return (
    <div className="answer-card" data-still={still || undefined} data-leaving={leaving || undefined}>
      {/* Focusable from script only: the field that had the focus hides on send. */}
      <p className="story-sent" tabIndex={-1}>
        <span className="story-bubble">{question}</span>
      </p>
      {problem && (
        <div className="problem" data-testid="ask-error">
          {problem}
        </div>
      )}
      {!problem && visible === 0 && waiting}
      {answer && visible > 0 && <Checked answer={answer} heading={heading} parts={order.slice(0, visible)} {...parts} />}
    </div>
  );
}

/** The checked answer's parts that show, in the hero's order: as many sources and sentences as have come. */
function Checked({ answer, heading: Heading, parts: shown, sources, head, actions, prefix = "" }: Parts & { answer: Answer; heading: Heading; parts: Part[] }) {
  const check = checkLine(answer);
  const filings = sources ? citedFilings(answer, sources) : [];
  const { input_tokens: input, output_tokens: output, cost_usd: cost } = answer.usage;
  const count = (part: Part) => shown.filter((each) => each === part).length;
  const has = (part: Part) => shown.includes(part);
  const said = count("sentence");
  return (
    <section className="card-reply" data-testid="answer" aria-labelledby={has("heading") ? `${prefix}answer-title` : undefined}>
      {has("read") && answer.reading && (
        <div className="story-row read-as" data-tone="read" data-testid="read-as">
          <Glyph d={GLYPHS.read} />
          <span>Read as</span>
          <ul>
            {readingChips(answer.reading).map((chip) => (
              <li key={chip}>{chip}</li>
            ))}
          </ul>
        </div>
      )}
      {has("source") && (
        <ol className="story-passages" aria-label="Cited passages">
          {answer.citations.slice(0, count("source")).map((citation, i) => (
            <li key={i} className="story-row" data-tone="passage">
              <span className="story-n" aria-hidden="true">
                {i + 1}
              </span>
              <span className="story-cite">
                <b>{sourceLabel(citation, sources) ?? `Source ${i + 1}`}</b>{" "}
                {citation.chunk_id ? <q>{citation.quote}</q> : citation.quote}
              </span>
            </li>
          ))}
        </ol>
      )}
      {has("filings") && (
        <ul className="card-filings" aria-label="Filings cited">
          {filings.map((filing) => (
            <li key={filing}>{filing}</li>
          ))}
        </ul>
      )}
      {has("heading") && (
        <div className="reply-head">
          <Heading id={`${prefix}answer-title`}>Answer</Heading>
          {answer.refused && <span className="badge warn">Not answered</span>}
          {head}
        </div>
      )}
      {said > 0 && (
        <div className="story-reply" data-state="checked">
          <div className="story-bubble">
            <AnswerText answer={answer} sources={sources} prefix={prefix} shown={said} />
          </div>
        </div>
      )}
      {has("check") && check && (
        <p className="story-row" data-tone="check">
          <Glyph d={GLYPHS.check} />
          <span>{check}</span>
        </p>
      )}
      {has("table") && <FigureChecks answer={answer} sources={sources} />}
      {has("warnings") && (
        <div className="warnings" data-testid="warnings">
          <p>
            <strong>Checks:</strong> validation changed the draft.
          </p>
          <ul>
            {answer.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
      {has("note") && <p className="note">Search skipped the reranker after a timeout, so passages keep their first order.</p>}
      {has("foot") && (
        <div className="card-foot">
          <p className="usage">
            {input.toLocaleString("en-US")} tokens in, {output.toLocaleString("en-US")} out, cost ${cost.toFixed(4)}
          </p>
          {actions && <div className="actions">{actions}</div>}
        </div>
      )}
    </section>
  );
}

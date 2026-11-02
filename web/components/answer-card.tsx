// The answer card, in the landing hero's look (docs/design.md): the question in a bubble, how the router read
// it, the reply, the check, then the numbered passages and the filings they come from. Ask fills it as the
// stream and the sources lookup report each part, never sooner; a stored answer and the demo's saved ones show
// it whole (`still`). Renders on the server or the client.
import type { ReactNode } from "react";

import { checkLine, citedFilings, readingChips, sourceLabel, type Answer } from "../lib/answer.ts";
import type { Sources } from "../lib/demo.ts";
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
  /** The draft as it streams; empty until its first words. */
  draft?: string | null;
  /** What went wrong, in place of a reply. */
  problem?: ReactNode;
  /** A stored or saved answer: whole at once, nothing moving in. */
  still?: boolean;
  level?: 2 | 3;
}

export function AnswerCard({ question, answer, draft, problem, still, level, ...parts }: Props) {
  const heading: Heading = level === 3 ? "h3" : "h2";
  const Heading = heading;
  const prefix = parts.prefix ?? "";
  const reading = answer?.reading;
  const waiting = !answer && !problem; // the reading's line is kept, empty, until the checked answer brings it
  return (
    <div className="answer-card" data-still={still || undefined}>
      <p className="story-sent">
        <span className="story-bubble">{question}</span>
      </p>
      {(reading || waiting) && (
        <div className="story-row read-as" data-tone="read" data-testid="read-as" data-pending={!reading || undefined}>
          <Glyph d={GLYPHS.read} />
          <span>Read as</span>
          <ul>{reading && readingChips(reading).map((chip) => <li key={chip}>{chip}</li>)}</ul>
        </div>
      )}
      {waiting && draft && (
        <section className="card-reply" data-testid="draft" aria-busy="true" aria-labelledby={`${prefix}draft-title`}>
          <Heading id={`${prefix}draft-title`} className="reply-head">
            Draft <span className="badge warn">citations not checked yet</span>
          </Heading>
          <div className="story-reply" data-state="draft">
            <p className="story-bubble draft-text">{draft}</p>
          </div>
        </section>
      )}
      {problem && (
        <div className="problem" data-testid="ask-error">
          {problem}
        </div>
      )}
      {answer && <Checked answer={answer} heading={heading} {...parts} />}
    </div>
  );
}

/** The checked answer: the reply with its citations, the check, the passages and their filings once the sources
    lookup reports them, then the number checks, the notes, the usage and the actions. */
function Checked({ answer, heading: Heading, sources, sourcesFailed, head, actions, prefix = "" }: Parts & { answer: Answer; heading: Heading }) {
  const check = checkLine(answer);
  const landed = answer.citations.length > 0 && (sources !== undefined || Boolean(sourcesFailed));
  const filings = sources ? citedFilings(answer, sources) : [];
  const { input_tokens: input, output_tokens: output, cost_usd: cost } = answer.usage;
  return (
    <section className="card-reply" data-testid="answer" aria-labelledby={`${prefix}answer-title`}>
      <div className="reply-head">
        <Heading id={`${prefix}answer-title`}>Answer</Heading>
        {answer.refused && <span className="badge warn">Not answered</span>}
        {head}
      </div>
      <div className="story-reply" data-state="checked">
        <div className="story-bubble">
          <AnswerText answer={answer} sources={sources} prefix={prefix} />
        </div>
      </div>
      {check && (
        <p className="story-row" data-tone="check">
          <Glyph d={GLYPHS.check} />
          <span>{check}</span>
        </p>
      )}
      {landed && (
        <ol className="story-passages" aria-label="Cited passages">
          {answer.citations.map((citation, i) => (
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
      {filings.length > 0 && (
        <ul className="card-filings" aria-label="Filings cited">
          {filings.map((filing) => (
            <li key={filing}>{filing}</li>
          ))}
        </ul>
      )}
      <FigureChecks answer={answer} sources={sources} />
      {answer.warnings.length > 0 && (
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
      {answer.degraded && (
        <p className="note">Search skipped the reranker after a timeout, so passages keep their first order.</p>
      )}
      <div className="card-foot">
        <p className="usage">
          {input.toLocaleString("en-US")} tokens in, {output.toLocaleString("en-US")} out, cost ${cost.toFixed(2)}
        </p>
        {actions && <div className="actions">{actions}</div>}
      </div>
    </section>
  );
}

// A validated answer with its citation links, number checks and source cards; renders on the server or client.
import {
  checksTitle,
  figureRows,
  findSource as find,
  locateQuote,
  periodEnded,
  readingChips,
  sourceLabel,
  splitFigures,
  splitMarkers,
  type Answer,
  type Reading,
} from "../lib/answer.ts";
import type { Sources } from "../lib/demo.ts";

export { sourceLabel };

type Citation = Answer["citations"][number];

/** How the router read the question, as quiet chips; nothing when the answer carries no reading. */
export function ReadAs({ reading }: { reading?: Reading | null }) {
  if (!reading) return null;
  return (
    <div className="read-as" data-testid="read-as">
      <span>Read as</span>
      <ul>
        {readingChips(reading).map((chip) => (
          <li key={chip}>{chip}</li>
        ))}
      </ul>
    </div>
  );
}

/** Each amount in the answer with its source's number. Validation removes a sentence whose amount no
    cited source holds, so every row is a match. */
function FigureChecks({ answer, sources }: { answer: Answer; sources?: Sources }) {
  if (!answer.checks.length) return null;
  const title = checksTitle(answer);
  // On a phone the table scrolls sideways in its own region, so the keyboard must reach it (axe).
  return (
    <div className="scroll checks" data-testid="checks" role="region" aria-label={title} tabIndex={0}>
      <table>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Figure</th>
            <th scope="col" className="num">
              In the answer
            </th>
            <th scope="col" className="num">
              Reported
            </th>
            <th scope="col">Result</th>
          </tr>
        </thead>
        <tbody>
          {figureRows(answer, sources).map((row, i) => (
            <tr key={i}>
              <th scope="row">{row.figure}</th>
              <td className="num">{row.written}</td>
              <td className="num reported">{row.reported}</td>
              <td className="match">Matches</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** "Source 1: NVDA 10-K FY2026, Item 1A", or "Source 1" until the sources load. */
function sourceName(n: number, citation: Citation, sources?: Sources): string {
  const label = sourceLabel(citation, sources);
  return label ? `Source ${n}: ${label}` : `Source ${n}`;
}

function Highlighted({ text, quote }: { text: string; quote: string }) {
  const span = locateQuote(text, quote);
  if (!span) return text;
  return (
    <>
      {text.slice(0, span.start)}
      <mark>{text.slice(span.start, span.end)}</mark>
      {text.slice(span.end)}
    </>
  );
}

/** Text with its figures under the highlighter. */
function Figures({ text }: { text: string }) {
  return splitFigures(text).map((piece, i) => (i % 2 ? <span key={i} className="figure">{piece}</span> : piece));
}

const number = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 10 });

function SourceCard({ n, citation, sources, prefix }: { n: number; citation: Citation; sources?: Sources; prefix: string }) {
  const id = `${prefix}source-${n}`;
  const { chunk, fact } = find(citation, sources);
  const label = sourceLabel(citation, sources);
  return (
    <article id={id} className="card" aria-labelledby={`${id}-title`} tabIndex={-1}>
      <h4 id={`${id}-title`}>
        <span className="source-n">Source {n}</span>
        {label && `: ${label}`}
      </h4>
      {chunk ? (
        <>
          <p className="period">{periodEnded(chunk.filing.fiscalPeriod, chunk.filing.periodEnd)}</p>
          <p className="meta">
            {chunk.filing.company.name}, {chunk.section.title}, filed {chunk.filing.filedOn}
          </p>
          <blockquote className="passage">
            <Highlighted text={chunk.text} quote={citation.quote} />
          </blockquote>
        </>
      ) : fact ? (
        <dl className="fact">
          <div>
            <dt>Label</dt>
            <dd>{fact.label}</dd>
          </div>
          <div className="value">
            <dt>Value</dt>
            <dd>
              {number(fact.value)} {fact.unit}
            </dd>
          </div>
          <div>
            <dt>Period</dt>
            <dd>{fact.periodStart ? `${fact.periodStart} to ${fact.periodEnd}` : fact.periodEnd}</dd>
          </div>
          <div className="accession">
            <dt>Accession</dt>
            <dd>{fact.accessionNumber}</dd>
          </div>
          <div>
            <dt>Company</dt>
            <dd>
              {fact.company.name} ({fact.company.ticker})
            </dd>
          </div>
        </dl>
      ) : citation.calculation ? (
        <>
          <p className="meta">
            From <a href={`#${prefix}source-${citation.calculation.inputs[0]}`}>source {citation.calculation.inputs[0]}</a> and{" "}
            <a href={`#${prefix}source-${citation.calculation.inputs[1]}`}>source {citation.calculation.inputs[1]}</a>; the answer
            model did none of this arithmetic.
          </p>
          <p className="calculation">
            <Figures text={citation.quote} />
          </p>
        </>
      ) : (
        <p className="meta">Quote: &ldquo;{citation.quote}&rdquo;</p>
      )}
      <p className="links">
        <a href={citation.filing_url}>
          Filing on sec.gov<span className="visually-hidden">, source {n}</span>
        </a>
        <a href={`#${prefix}answer-text`}>
          Back to the answer<span className="visually-hidden"> from source {n}</span>
        </a>
      </p>
    </article>
  );
}

interface Props {
  answer: Answer;
  sources?: Sources;
  sourcesFailed?: boolean;
  prefix?: string;
}

/** The answer's text: figures under the highlighter, each citation a link to its source card. */
export function AnswerText({ answer, sources, prefix = "" }: Props) {
  const parts = splitMarkers(answer.answer, answer.citations.length);
  return (
    <p className="answer-text" id={`${prefix}answer-text`} tabIndex={-1}>
      {parts.map((part, i) =>
        typeof part === "number" ? (
          // The box shows the number; the brackets stay, at zero size, so copied text reads "[1]".
          <a key={i} href={`#${prefix}source-${part}`} aria-label={sourceName(part, answer.citations[part - 1], sources)}>
            <span className="bracket">[</span>
            {part}
            <span className="bracket">]</span>
          </a>
        ) : (
          <Figures key={i} text={part} />
        ),
      )}
    </p>
  );
}

/** The answer itself: its text with citation links, then warnings, notes and usage. */
export function AnswerMain(props: Props) {
  const { answer } = props;
  const { input_tokens: input, output_tokens: output, cost_usd: cost } = answer.usage;
  return (
    <div className="answer-main">
      {answer.refused && <p className="tag">Not answered</p>}
      <AnswerText {...props} />
      <FigureChecks answer={answer} sources={props.sources} />
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
      <p className="usage">
        {input.toLocaleString("en-US")} tokens in, {output.toLocaleString("en-US")} out, cost ${cost.toFixed(2)}
      </p>
    </div>
  );
}

/** The sources panel, one card per citation; nothing when the answer cites nothing. */
export function SourceList({ answer, sources, sourcesFailed = false, prefix = "" }: Props) {
  if (answer.citations.length === 0) return null;
  return (
    <section className="sources" aria-labelledby={`${prefix}sources-title`}>
      <h3 id={`${prefix}sources-title`}>Sources</h3>
      {sourcesFailed && (
        <p className="note" data-testid="sources-error">
          Sources could not be loaded.
        </p>
      )}
      {answer.citations.map((citation, i) => (
        <SourceCard key={i} n={i + 1} citation={citation} sources={sources} prefix={prefix} />
      ))}
    </section>
  );
}

export function AnswerView(props: Props) {
  return (
    <div className="answer">
      <AnswerMain {...props} />
      <SourceList {...props} />
    </div>
  );
}

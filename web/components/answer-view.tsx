// A validated answer with its citation links and source cards; renders on the server or client.
import { formLabel, locateQuote, splitMarkers, type Answer } from "../lib/answer.ts";
import type { Sources } from "../lib/demo.ts";

type Citation = Answer["citations"][number];

function find(citation: Citation, sources?: Sources) {
  return {
    chunk: citation.chunk_id ? sources?.chunks.find((chunk) => chunk.id === citation.chunk_id) : undefined,
    fact: citation.fact_id ? sources?.facts.find((fact) => fact.id === citation.fact_id) : undefined,
  };
}

/** "Source 1: NVDA 10-K FY2026, Item 1A", or "Source 1" until the sources load. */
function sourceName(n: number, citation: Citation, sources?: Sources): string {
  const { chunk, fact } = find(citation, sources);
  if (chunk) {
    const { company, formType, fiscalYear } = chunk.filing;
    return `Source ${n}: ${company.ticker} ${formLabel(formType)} FY${fiscalYear}, Item ${chunk.section.item}`;
  }
  // A fact's fiscal year is its reporting filing's, so the period end names the value's own date.
  if (fact) return `Source ${n}: ${fact.company.ticker} fact, ${fact.label}, period ending ${fact.periodEnd}`;
  return `Source ${n}`;
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

const number = (value: number) => value.toLocaleString("en-US", { maximumFractionDigits: 10 });

function SourceCard({ n, citation, sources, prefix }: { n: number; citation: Citation; sources?: Sources; prefix: string }) {
  const id = `${prefix}source-${n}`;
  const { chunk, fact } = find(citation, sources);
  return (
    <article id={id} className="card" aria-labelledby={`${id}-title`} tabIndex={-1}>
      <h4 id={`${id}-title`}>{sourceName(n, citation, sources)}</h4>
      {chunk ? (
        <>
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
          <div>
            <dt>Value</dt>
            <dd>
              {number(fact.value)} {fact.unit}
            </dd>
          </div>
          <div>
            <dt>Period</dt>
            <dd>{fact.periodStart ? `${fact.periodStart} to ${fact.periodEnd}` : fact.periodEnd}</dd>
          </div>
          <div>
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

export function AnswerView({
  answer,
  sources,
  sourcesFailed = false,
  prefix = "",
}: {
  answer: Answer;
  sources?: Sources;
  sourcesFailed?: boolean;
  prefix?: string;
}) {
  const parts = splitMarkers(answer.answer, answer.citations.length);
  const { input_tokens: input, output_tokens: output, cost_usd: cost } = answer.usage;
  return (
    <div className="answer">
      {answer.refused && <p className="tag">Not answered</p>}
      <p className="answer-text" id={`${prefix}answer-text`} tabIndex={-1}>
        {parts.map((part, i) =>
          typeof part === "number" ? (
            <a key={i} href={`#${prefix}source-${part}`} aria-label={sourceName(part, answer.citations[part - 1], sources)}>
              [{part}]
            </a>
          ) : (
            part
          ),
        )}
      </p>
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
      {answer.citations.length > 0 && (
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
      )}
    </div>
  );
}

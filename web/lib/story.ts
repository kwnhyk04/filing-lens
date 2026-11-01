// The hero's story: one saved answer from the demo snapshot, from golden v1's test run. Its question, how
// the router read it, the passages it cites (form, year and item), its answer and its number check.
import { formLabel, readingChips, sourceLabel } from "./answer.ts";
import type { Snapshot } from "./demo.ts";

/** x12: Eli Lilly's revenue growth, answered from two passages of its 10-K. */
export const STORY = "x12";

export function heroStory(snapshot: Snapshot, id = STORY) {
  const saved = snapshot.answers.find((item) => item.id === id);
  if (!saved) throw new Error(`The demo snapshot has no answer ${id}`);
  const { answer } = saved;
  if (answer.refused || !answer.citations.length) throw new Error(`${id} is refused or cites nothing`);
  const chunks = answer.citations.map((citation) => snapshot.sources.chunks.find((item) => item.id === citation.chunk_id));
  const passages = answer.citations.map((citation, i) => {
    const chunk = chunks[i];
    const label = sourceLabel(citation, snapshot.sources);
    if (!chunk || !label) throw new Error(`${id} cites a source that is not a passage`);
    return { n: i + 1, label, item: chunk.section.item, quote: citation.quote };
  });
  const filing = passages[0].label.replace(/, Item .*$/, "");
  if (passages.some((passage) => !passage.label.startsWith(`${filing},`))) throw new Error(`${id} cites two filings`);
  const ticker = filing.split(" ")[0];
  const others = snapshot.companies
    .filter((company) => company.ticker !== ticker)
    .flatMap(({ ticker, filings }) => filings.edges.map(({ node }) => `${ticker} ${formLabel(node.formType)} FY${node.fiscalYear}`));
  return {
    question: saved.question,
    answer,
    reading: answer.reading ? readingChips(answer.reading) : [],
    passages,
    checks: answer.checks.map((check) => ({ n: check.citation, text: check.text, value: check.source_value })),
    /** The cited passages alone, for the answer's citation names. */
    sources: { chunks: chunks.filter((chunk) => chunk !== undefined), facts: [] },
    /** "LLY 10-K FY2025": the filing every passage comes from. */
    filing,
    /** The snapshot's other filings, as form and year, to float around the story. */
    others,
  };
}

export type HeroStory = ReturnType<typeof heroStory>;

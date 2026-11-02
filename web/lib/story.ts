// The hero's stories: saved answers from the demo snapshot, from golden v1's test run. Each has its question,
// how the router read it, the sources it cites (a passage with form, year and item, or an XBRL fact with its
// value), its answer and its number checks. The still tells x12; the moving hero loops through LOOP.
import { findSource, formLabel, listed, readingChips, sourceLabel } from "./answer.ts";
import type { Snapshot } from "./demo.ts";

/** x12: Eli Lilly's revenue growth, answered from two passages of its 10-K: the still, and the loop's first. */
export const STORY = "x12";
/** x04: Amazon's reportable segments, from one passage of its 10-K: the overview's saved answer. */
export const QUOTE = "x04";
/** The moving hero's loop, no company twice and not QUOTE, which the overview just below shows: x12, then
    Apple's revenue (a fact) and Alphabet's revenue against Meta's (two facts from two filings). */
export const LOOP = ["x12", "n01", "c02"];
const WORDS = ["One", "Two", "Three", "Four"];

/** "AMZN 10-K FY2025": a filing as form and year. */
const named = (ticker: string, form: string, year: number) => `${ticker} ${formLabel(form)} FY${year}`;

export function heroStory(snapshot: Snapshot, id = STORY) {
  const saved = snapshot.answers.find((item) => item.id === id);
  if (!saved) throw new Error(`The demo snapshot has no answer ${id}`);
  const { answer } = saved;
  if (answer.refused || !answer.citations.length) throw new Error(`${id} is refused or cites nothing`);
  const found = answer.citations.map((citation) => findSource(citation, snapshot.sources));
  const passages = answer.citations.map((citation, i) => {
    const { chunk, fact } = found[i];
    const label = sourceLabel(citation, snapshot.sources);
    const n = i + 1;
    if (chunk && label) {
      const { company, formType, fiscalYear } = chunk.filing;
      const filing = named(company.ticker, formType, fiscalYear);
      return { n, kind: "passage" as const, label, filing, item: chunk.section.item, quote: citation.quote };
    }
    // A fact names its filing by accession number; the snapshot lists that filing under its company.
    const node =
      fact &&
      snapshot.companies
        .find((company) => company.ticker === fact.company.ticker)
        ?.filings.edges.find((edge) => edge.node.accessionNumber === fact.accessionNumber)?.node;
    if (!fact || !node || !label) throw new Error(`${id} cites a source that is not a passage or a fact`);
    return { n, kind: "fact" as const, label, filing: named(fact.company.ticker, node.formType, node.fiscalYear), quote: citation.quote };
  });
  const filings = [...new Set(passages.map((source) => source.filing))];
  const cited = new Set(filings.map((filing) => filing.split(" ")[0]));
  const others = snapshot.companies
    .filter((company) => !cited.has(company.ticker))
    .flatMap(({ ticker, filings }) => filings.edges.map(({ node }) => named(ticker, node.formType, node.fiscalYear)));
  return {
    question: saved.question,
    answer,
    reading: answer.reading ? readingChips(answer.reading) : [],
    /** The cited sources in citation order: passages, or facts whose quote is their value as published. */
    passages,
    checks: answer.checks.map((check) => ({ n: check.citation, text: check.text, value: check.source_value })),
    /** The cited passages and facts alone, for the answer's citation names. */
    sources: {
      chunks: found.flatMap(({ chunk }) => (chunk ? [chunk] : [])),
      facts: found.flatMap(({ fact }) => (fact ? [fact] : [])),
    },
    /** "LLY 10-K FY2025", or "GOOGL 10-K FY2025 and META 10-K FY2025": every filing the sources come from. */
    filing: listed(filings),
    filings,
    /** The snapshot's other filings, as form and year, to float around the story. */
    others,
  };
}

export type HeroStory = ReturnType<typeof heroStory>;

export const heroStories = (snapshot: Snapshot) => LOOP.map((id) => heroStory(snapshot, id));

/** What a story cites, in words: its passages, its facts, or both. */
const cites = (story: HeroStory) => {
  const kinds = new Set(story.passages.map((source) => source.kind));
  return kinds.size > 1 ? "source" : kinds.has("fact") ? "fact" : "passage";
};

/** The moving story's beats: what the caption says at each, and the steps' names. */
export function storyBeats(story: HeroStory) {
  const n = story.passages.length;
  const noun = cites(story);
  const counted = `${WORDS[n - 1] ?? n} ${noun}${n === 1 ? "" : "s"}`;
  return [
    { cue: "A question about a filing.", label: "Ready" },
    { cue: "FilingLens reads it: the company, the years, the kind of question.", label: "Read" },
    { cue: `Read as ${story.reading.join(" · ")}.`, label: "Ask" },
    { cue: `${counted} from ${story.filing} ${n === 1 ? "holds" : "hold"} the answer.`, label: "Find" },
    {
      cue: `Each sentence cites its ${noun}, and a check matches every ${noun === "fact" ? "amount" : "quote and amount"}.`,
      label: "Answer",
    },
    { cue: "An answer you can check.", label: "Done" },
  ];
}

/** "Checked: 56 percent matches source 2, and every quote matches its passage word for word.": each amount
    with the source holding it, then the quotes, when the story cites a passage. */
export function checkLine(story: HeroStory): string {
  const amounts = listed(story.checks.map((check) => `${check.text} matches source ${check.n}`));
  if (!story.passages.some((source) => source.kind === "passage")) return `Checked: ${amounts}.`;
  return `Checked: ${amounts ? `${amounts}, and ` : ""}every quote matches its passage word for word.`;
}

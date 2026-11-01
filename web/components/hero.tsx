// The landing page's hero, after Prompt Bond (21st.dev, MIT; docs/third-party.md): the headline in two
// voices, what FilingLens covers, and one saved answer told as a story. The still is that story at its end,
// in plain HTML: the first paint everywhere, and all that phones and reduced motion get. A desktop swaps in
// the moving story once the page has loaded (hero-motion.tsx).
import type { HeroStory } from "../lib/story.ts";
import { HeroMotion } from "./hero-motion.tsx";
import { StoryPanel } from "./story-panel.tsx";

const LINES = ["Every answer.", "Straight from the filing."];

/** A line's letters, one span each inside a span per word: the moving hero weighs each by the pointer. */
function Letters({ text }: { text: string }) {
  return text.split(/(\s+)/).map((word, i) =>
    /^\s+$/.test(word) ? (
      word
    ) : (
      <span key={i} className="hero-word">
        {[...word].map((letter, j) => (
          <span key={j}>{letter}</span>
        ))}
      </span>
    ),
  );
}

export function Hero({ story, companies }: { story: HeroStory; companies: number }) {
  return (
    <section className="hero" aria-labelledby="hero-title">
      <div className="hero-field" aria-hidden="true" />
      <div className="hero-stage" aria-hidden="true" />
      <h1 id="hero-title" className="hero-title">
        <span className="visually-hidden">{LINES.join(" ")}</span>
        {LINES.map((line, i) => (
          <span key={line} className={`hero-line hero-line-${i + 1}`} aria-hidden="true">
            <Letters text={line} />
          </span>
        ))}
      </h1>
      <p className="hero-lead">
        Ask a question about a fixed set of {companies} companies&apos; 10-K SEC filings. FilingLens finds the
        passages and answers with citations you can check.
      </p>
      <figure className="hero-story">
        <div className="story-still" data-testid="story-still">
          <StoryPanel story={story} prefix="hero-" />
        </div>
        <HeroMotion />
        <figcaption>A saved answer from golden v1&apos;s test run, as the demo shows it.</figcaption>
      </figure>
    </section>
  );
}

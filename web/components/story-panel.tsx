// The hero story's panel: the question, how the router read it, the passages it cites (form, year, item and
// quote), the answer with its citation links, and the number check. The still shows it whole; the moving
// story reveals one row at a time through `rowRef`, with ids of its own (`prefix`).
import type { HeroStory } from "../lib/story.ts";
import { AnswerText } from "./answer-view.tsx";

type Ref<T> = (element: T | null) => void;

interface Props {
  story: HeroStory;
  prefix: string;
  /** The moving story's handle on row `i`: 0 the question, 1 the reading, then the passages, the answer, the check. */
  rowRef?: (i: number) => Ref<HTMLElement>;
  replyRef?: Ref<HTMLDivElement>;
}

// Lucide's file-text and check (ISC licence, docs/third-party.md); a scan for the reading.
const GLYPHS = {
  read: "M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M7 12h10",
  check: "M20 6 9 17l-5-5",
};

function Glyph({ d }: { d: string }) {
  return (
    <span className="story-glyph" aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false">
        <path d={d} />
      </svg>
    </span>
  );
}

/** "a", "a and b", "a, b and c". */
const listed = (items: string[]) => (items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`);

export function StoryPanel({ story, prefix, rowRef, replyRef }: Props) {
  const passages = story.passages.length;
  return (
    <div className="story-panel">
      <p className="story-sent" ref={rowRef?.(0)}>
        <span className="story-bubble">{story.question}</span>
      </p>
      <p className="story-row" data-tone="read" ref={rowRef?.(1)}>
        <Glyph d={GLYPHS.read} />
        <span>
          Read as <b>{story.reading.join(" · ")}</b>
        </span>
      </p>
      <ol className="story-passages">
        {story.passages.map((passage, i) => (
          <li
            key={passage.n}
            id={`${prefix}source-${passage.n}`}
            className="story-row"
            data-tone="passage"
            tabIndex={-1}
            ref={rowRef?.(2 + i)}
          >
            <span className="story-n" aria-hidden="true">
              {passage.n}
            </span>
            <span className="story-cite">
              <b>{passage.label}</b> <q>{passage.quote}</q>
            </span>
          </li>
        ))}
      </ol>
      <div className="story-reply" ref={rowRef?.(2 + passages)}>
        <div className="story-bubble" ref={replyRef}>
          <AnswerText answer={story.answer} sources={story.sources} prefix={prefix} />
        </div>
      </div>
      <p className="story-row" data-tone="check" ref={rowRef?.(3 + passages)}>
        <Glyph d={GLYPHS.check} />
        <span>
          Checked:{" "}
          {story.checks.length > 0 && (
            <>
              {listed(story.checks.map((check) => `${check.text} matches source ${check.n}`))}, and{" "}
            </>
          )}
          every quote matches its passage word for word.
        </span>
      </p>
    </div>
  );
}

// Recent questions under Ask's answer: this sign-in's earlier questions, newest first. A click shows the
// stored answer again, without a model call. Hidden while there are none.
import { clockTime, type RecentAnswer } from "../lib/answer.ts";

interface Props {
  items: RecentAnswer[]; // without the one on screen
  busy: boolean;
  onPick: (item: RecentAnswer) => void;
}

export function RecentQuestions({ items, busy, onPick }: Props) {
  if (!items.length) return null;
  return (
    <section className="recent" aria-labelledby="recent-title" data-testid="recent">
      <h2 id="recent-title">Recent questions</h2>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            {/* aria-disabled, not disabled, while answering: a disabled button would drop the focus */}
            <button type="button" aria-disabled={busy || undefined} onClick={() => !busy && onPick(item)}>
              <span>{item.question}</span>
              <time dateTime={item.answered_at}>{clockTime(item.answered_at)}</time>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

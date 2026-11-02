"use client";
// Ask, the live version of the landing hero: the stage at the top holds the question field, then the question in
// its bubble, the draft, the checked answer and the passages it cites, each when the stream or the sources lookup
// reports it. Below it, this sign-in's Recent questions and the answer's Sources, each in a card. On a desktop
// with a graphics card the hero's moving story plays over the same states (stage-motion, ask-live.tsx).
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import {
  answerWithSources,
  createSseParser,
  storedLine,
  timingLine,
  type Answer,
  type AnswerEvent,
  type RecentAnswer,
} from "../lib/answer.ts";
import type { Sources } from "../lib/demo.ts";
import { citedThings, stagePhase, type Thing } from "../lib/stage.ts";
import { AnswerCard } from "./answer-card.tsx";
import { SourceList, sourceLabel } from "./answer-view.tsx";
import { StageMotion } from "./hero-motion.tsx";
import { QuoteInView } from "./quote-in-view.tsx";
import { RecentQuestions } from "./recent-questions.tsx";

interface Problem {
  code?: string;
  detail?: string;
  retryAfter?: number;
  requestId?: string;
}

interface Notice {
  text: string;
  demo?: boolean;
}

/** What the browser timed, from the question's send: its first draft text and its checked answer. */
interface Timing {
  firstWordsMs?: number;
  completeMs: number;
}

function notice(status: number, problem: Problem): Notice {
  if (problem.code === "offline") return { text: "The API is offline right now.", demo: true };
  if (problem.code === "misconfigured") {
    return { text: `The API refused this web server's key. Request id: ${problem.requestId ?? "unknown"}.` };
  }
  if (status === 429) return { text: `Too many questions. Try again in ${problem.retryAfter ?? 60} s.` };
  if (status === 503 && problem.retryAfter === undefined) {
    return { text: "Live answers are switched off on this server.", demo: true };
  }
  if (status === 503) return { text: `The service is busy. Try again in ${problem.retryAfter} s.` };
  return { text: problem.detail ?? `The answer failed (HTTP ${status}).` };
}

/** Reads the event stream; deltas go to `onDelta` as they arrive. `storedAt` marks an answer from earlier. */
async function readEvents(body: ReadableStream<Uint8Array>, onDelta: (text: string) => void) {
  const result: { answer?: Answer; storedAt?: string | null; failed?: string } = {};
  const push = createSseParser((data) => {
    const event = JSON.parse(data) as AnswerEvent;
    if (event.type === "delta") onDelta(event.text);
    else if (event.type === "completed") {
      result.answer = event.answer;
      result.storedAt = event.stored_at ?? null; // an API from before recent questions sends none
    } else result.failed = event.problem.detail ?? "The answer failed.";
  });
  const decoder = new TextDecoder();
  const reader = body.getReader();
  for (let read = await reader.read(); !read.done; read = await reader.read()) {
    push(decoder.decode(read.value, { stream: true }));
  }
  return result;
}

const sourceCount = (count: number) => `${count} source${count === 1 ? "" : "s"}`;

/** Enter sends, as the form's own submit (its length check first); Shift+Enter and an IME's Enter type on. */
function sendOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
  if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
  event.preventDefault();
  event.currentTarget.form?.requestSubmit();
}

/** `samples`: questions the filings can answer, offered on the empty stage; a click only fills the field.
    `covered`: the coverage list's filings, which float round the stage while an answer is on its way. */
export function Ask({ samples, covered }: { samples: string[]; covered: Thing[] }) {
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asked, setAsked] = useState<string | null>(null); // the question whose answer is on screen
  const [storedAt, setStoredAt] = useState<string | null>(null); // when that answer is from earlier
  const [recent, setRecent] = useState<RecentAnswer[]>([]);
  const [sources, setSources] = useState<Sources>();
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [problem, setProblem] = useState<Notice | null>(null);
  const [status, setStatus] = useState("");
  const [timing, setTiming] = useState<Timing | null>(null);
  const [turn, setTurn] = useState(0); // each question's card is a new one, so what arrives moves in afresh
  const running = useRef<AbortController | null>(null);
  const focusAnswer = useRef(false);
  const form = useRef<HTMLFormElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  // Leaving Ask, through a header link, stops its answer stream and its sources lookup.
  useEffect(() => () => running.current?.abort(), []);
  // In the browser only, so the times read in its time zone and the server renders no list.
  useEffect(() => void loadRecent(), []);
  // A recent question's answer takes the focus once it is on screen, as Back to the answer does.
  useEffect(() => {
    if (!answer || !focusAnswer.current) return;
    focusAnswer.current = false;
    document.getElementById("answer-text")?.focus();
  }, [answer]);

  /** This sign-in's recent questions. Any failure hides the list, an API without them included. */
  async function loadRecent() {
    try {
      const found = await fetch("/api/recent");
      setRecent(found.ok ? ((await found.json()) as { items: RecentAnswer[] }).items : []);
    } catch {
      setRecent([]);
    }
  }

  function fail(failure: Notice) {
    setDraft(null);
    setProblem(failure);
    setStatus(failure.text);
  }

  /** An answer on screen: a new one, or one from earlier (stored), whose header then says when it was given. */
  function show(done: Answer, stored: string | null) {
    setDraft(null);
    setAnswer(done);
    setStoredAt(stored);
    const ready = stored ? "Answer from earlier in this session" : "Answer ready";
    setStatus(done.refused ? "Not answered; the reason is below." : `${ready}, with ${sourceCount(done.citations.length)}.`);
  }

  /** The cited chunks and facts. A failure keeps the answer and adds a note; it never throws. */
  async function showSources(done: Answer, signal: AbortSignal) {
    const chunkIds = done.citations.flatMap((c) => (c.chunk_id ? [c.chunk_id] : []));
    const factIds = done.citations.flatMap((c) => (c.fact_id ? [c.fact_id] : []));
    if (!chunkIds.length && !factIds.length) return;
    try {
      const found = await fetch("/api/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chunkIds, factIds }),
        signal,
      });
      if (found.ok) return setSources((await found.json()) as Sources);
    } catch {
      if (signal.aborted) return;
    }
    setSourcesFailed(true);
    setStatus((ready) => `${ready} Sources could not be loaded.`);
  }

  /** Asks through the BFF; `fresh` (Ask again) answers anew instead of giving back the earlier answer. */
  async function run(question: string, fresh = false) {
    running.current?.abort(); // a new question stops the one before
    const controller = new AbortController();
    running.current = controller;
    const { signal } = controller;
    setBusy(true);
    setTurn((n) => n + 1);
    setAsked(question);
    setDraft("");
    setAnswer(null);
    setStoredAt(null);
    setSources(undefined);
    setSourcesFailed(false);
    setProblem(null);
    setTiming(null);
    setStatus("Answering.");
    const started = performance.now();
    let firstWordsMs: number | undefined;
    try {
      const response = await fetch("/api/answers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, fresh }),
        signal,
      });
      if (response.status === 401) return window.location.assign("/login?next=%2Fask");
      if (!response.ok || !response.body) {
        return fail(notice(response.status, await response.json().catch(() => ({}))));
      }
      const result = await readEvents(response.body, (text) => {
        firstWordsMs ??= performance.now() - started;
        setDraft((sofar) => (sofar ?? "") + text);
      });
      if (!result.answer) return fail({ text: result.failed ?? "The answer stopped before it finished." });
      const done = result.answer;
      show(done, result.storedAt ?? null);
      if (!result.storedAt) setTiming({ firstWordsMs, completeMs: performance.now() - started });
      if (!result.storedAt && !done.refused) void loadRecent(); // the API has just kept it
      await showSources(done, signal);
    } catch {
      // Only the stream lands here, since showSources keeps its own failures; an abort shows nothing.
      if (!signal.aborted) fail({ text: "The web server could not be reached.", demo: true });
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  /** The question goes into the stage's bubble and the field clears: it shows once. */
  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const question = String(new FormData(event.currentTarget).get("question") ?? "").trim();
    event.currentTarget.reset();
    await run(question);
  }

  /** A recent question: its stored answer with its reading, number checks and sources, and no model call. */
  function pick(item: RecentAnswer) {
    running.current?.abort(); // a sources lookup still running stops
    const controller = new AbortController();
    running.current = controller;
    setTurn((n) => n + 1);
    setAsked(item.question);
    setProblem(null);
    setTiming(null);
    setSources(undefined);
    setSourcesFailed(false);
    show(item.answer, item.answered_at);
    focusAnswer.current = true;
    void showSources(item.answer, controller.signal);
  }

  /** The answer and its sources on the clipboard, as plain text; the status line says how it went. */
  async function copy(done: Answer) {
    const labels = done.citations.map((citation) => sourceLabel(citation, sources));
    try {
      await navigator.clipboard.writeText(answerWithSources(done, labels));
      setStatus("Copied the answer with its sources.");
    } catch {
      setStatus("Copying failed. Select the answer to copy it.");
    }
  }

  /** Back to the empty stage, with the focus in the field; a sources lookup still running stops. */
  function startOver() {
    running.current?.abort();
    setBusy(false); // an aborted question leaves busy alone, so it is cleared here
    setAnswer(null);
    setAsked(null);
    setStoredAt(null);
    setSources(undefined);
    setSourcesFailed(false);
    setTiming(null);
    setStatus("");
    form.current?.reset();
    box.current?.focus();
  }

  // The question on screen is left out of the list: by its words, or by its stored time for a repeat.
  const others = recent.filter((item) => item.question !== asked && item.answered_at !== storedAt);
  const phase = stagePhase({ asked, answer, sources, sourcesFailed, problem: problem !== null });
  // Kept between renders, so the moving stage re-plots only when the sources change.
  const cited = useMemo(() => (answer && sources ? citedThings(answer, sources) : []), [answer, sources]);

  // The DOM order is the reading order: the field, the stage's answer, then Recent questions and Sources.
  return (
    <div className="ask">
      <section className="stage" aria-label="Ask about the filings" data-phase={phase} data-motion="still">
        <div className="stage-field" aria-hidden="true" />
        <div className="stage-layer" aria-hidden="true" />
        <form ref={form} onSubmit={ask} className="stage-ask">
          <label htmlFor="question" className="visually-hidden">
            Your question
          </label>
          <div className="stage-input">
            <textarea
              ref={box}
              id="question"
              name="question"
              rows={2}
              required
              minLength={3}
              maxLength={1000}
              placeholder="Ask about a company's 10-K..."
              aria-describedby="question-help"
              onKeyDown={sendOnEnter}
            />
            {/* aria-disabled, not disabled: a disabled button would drop the keyboard user's focus */}
            <button type="submit" className="stage-send" aria-disabled={busy || undefined}>
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
              <span className={busy ? undefined : "visually-hidden"}>{busy ? "Answering…" : "Ask"}</span>
            </button>
          </div>
          <p id="question-help" className="help">
            About the tracked companies&apos; filings: 3 to 1,000 characters. Enter sends; Shift+Enter starts a new line.
          </p>
        </form>
        {phase === "empty" && samples.length > 0 && (
          <section className="samples" aria-labelledby="samples-title" data-testid="samples">
            <h2 id="samples-title">Try a question the filings can answer</h2>
            <ul>
              {samples.map((sample) => (
                <li key={sample}>
                  <button
                    type="button"
                    className="secondary small"
                    onClick={() => {
                      if (!box.current) return;
                      box.current.value = sample;
                      box.current.focus();
                    }}
                  >
                    {sample}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        <p role="status" className="status" data-testid="ask-status">
          {status}
        </p>
        {/* Always there, empty until a question: the moving stage measures itself round it. */}
        <div className="stage-panel">
          {asked !== null && (
            <AnswerCard
              key={turn}
              question={asked}
              draft={draft}
              answer={answer}
              sources={sources}
              sourcesFailed={sourcesFailed}
              still={storedAt !== null}
              problem={
                problem && (
                  <>
                    <p>{problem.text}</p>
                    {problem.demo && (
                      <p>
                        <Link href="/demo">See the saved answers</Link>
                      </p>
                    )}
                  </>
                )
              }
              head={
                storedAt ? (
                  <p className="timings" data-testid="stored">
                    {storedLine(storedAt)}
                  </p>
                ) : (
                  timing &&
                  answer && (
                    <p className="timings" data-testid="timings">
                      {timingLine(timing.firstWordsMs, timing.completeMs, answer.citations.length, answer.checks.length > 0)}
                    </p>
                  )
                )
              }
              actions={
                answer && (
                  <>
                    {answer.citations.length > 0 && (
                      <button type="button" className="secondary small" onClick={() => copy(answer)}>
                        Copy answer with sources
                      </button>
                    )}
                    {storedAt && (
                      <button
                        type="button"
                        className="secondary small"
                        aria-disabled={busy || undefined}
                        onClick={() => !busy && run(asked, true)}
                      >
                        Ask again
                      </button>
                    )}
                    <button type="button" className="secondary small" onClick={startOver}>
                      New question
                    </button>
                  </>
                )
              }
            />
          )}
        </div>
        {/* While it reads: the coverage list's filings, none of them claimed; the moving stage floats them. */}
        {phase === "reading" && (
          <div className="stage-reading">
            <p>Reading the filings…</p>
            {covered.length > 0 && (
              <ul className="stage-covered" aria-label="Filings FilingLens covers">
                {covered.map((thing) => (
                  <li key={thing.filing}>{thing.filing}</li>
                ))}
              </ul>
            )}
          </div>
        )}
        <StageMotion phase={phase} turn={turn} covered={covered} cited={cited} />
      </section>
      <div className="ask-below">
        <div className="ask-card ask-recent" data-testid="recent-card">
          {others.length > 0 ? (
            <RecentQuestions items={others} busy={busy} onPick={pick} />
          ) : (
            <p className="help">Questions you ask will appear here.</p>
          )}
        </div>
        <div className="ask-card ask-sources" data-testid="sources-card">
          {answer && answer.citations.length > 0 ? (
            <SourceList answer={answer} sources={sources} sourcesFailed={sourcesFailed} />
          ) : (
            <p className="help">{answer ? "This answer cites no sources." : "Sources for your answer appear here."}</p>
          )}
        </div>
      </div>
      <QuoteInView />
    </div>
  );
}

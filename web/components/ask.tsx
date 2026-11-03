"use client";
// Ask, the live version of the landing hero's story (docs/design.md). The field sits at the top of the empty stage.
// On send it hides, and the card, with the question's bubble, takes the top: "Reading the filings…" until the
// checked answer and its sources are both in. Then, on a desktop that allows motion, the moving stage (ask-live.tsx)
// pulls the cited filings in and the parts arrive one by one in the hero's order (Read as, each source, the filing
// tags, the heading, each sentence, the check, the numbers, the foot), each growing the card to take it; phones and
// reduced motion get the same order at once. Once the answer is done the field comes back under the card. Below the
// stage, Recent questions and Sources, each only when it holds something.
import Link from "next/link";
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { flushSync } from "react-dom";

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
import { citedThings, ENTER_MS, FLY_MS, LEAVE_MS, revealParts, revealTimes, stagePhase, stageView, type Thing } from "../lib/stage.ts";
import { AnswerCard } from "./answer-card.tsx";
import { SourceList, sourceLabel } from "./answer-view.tsx";
import { DESKTOP, StageMotion } from "./hero-motion.tsx";
import { QuoteInView } from "./quote-in-view.tsx";
import { RecentQuestions } from "./recent-questions.tsx";
import { Glyph, GLYPHS } from "./story-panel.tsx";

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

/** Reads the event stream; `onDelta` hears each piece of the draft. `storedAt` marks an answer from earlier. */
async function readEvents(body: ReadableStream<Uint8Array>, onDelta: () => void) {
  const result: { answer?: Answer; storedAt?: string | null; failed?: string } = {};
  const push = createSseParser((data) => {
    const event = JSON.parse(data) as AnswerEvent;
    if (event.type === "delta") onDelta();
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

/** The status line once an answer is on screen. */
function readyLine(done: Answer, storedAt: string | null, sourcesFailed: boolean): string {
  if (done.refused) return "Not answered; the reason is below.";
  const ready = storedAt ? "Answer from earlier in this session" : "Answer ready";
  return `${ready}, with ${sourceCount(done.citations.length)}.${sourcesFailed ? " Sources could not be loaded." : ""}`;
}

/** Where any BFF call's 401 sends the page: the session ended, so sign in again and come back. */
const SIGN_IN = "/login?next=%2Fask";
/** The sources lookup gives up after this: the answer waits for it, and the BFF's own call stops at 5 s. */
const SOURCES_TIMEOUT_MS = 6_000;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
/** An element's top left on the page, so a scroll in between does not move it. */
const onPage = (element: Element) => {
  const { left, top } = element.getBoundingClientRect();
  return { x: left + scrollX, y: top + scrollY };
};

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
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [asked, setAsked] = useState<string | null>(null); // the question whose card is on screen
  const [storedAt, setStoredAt] = useState<string | null>(null); // when that answer is from earlier
  const [whole, setWhole] = useState(false); // a recent question's answer: shown whole, never the sequence
  const [recent, setRecent] = useState<RecentAnswer[]>([]);
  const [sources, setSources] = useState<Sources>();
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [problem, setProblem] = useState<Notice | null>(null);
  const [status, setStatus] = useState("");
  const [timing, setTiming] = useState<Timing | null>(null);
  const [turn, setTurn] = useState(0); // each question's card is a new one
  const [reveal, setReveal] = useState<{ turn: number; pull: boolean; moving: boolean } | null>(null); // this turn's
  const [step, setStep] = useState(Infinity); // how many of the card's parts show
  const [leaving, setLeaving] = useState(false);
  const running = useRef<AbortController | null>(null);
  const timers = useRef<number[]>([]);
  const focusAnswer = useRef(false);
  const flyFrom = useRef<{ x: number; y: number } | null>(null);
  const cardHeight = useRef(0); // the card's height after the last step, which the next one grows from
  const stage = useRef<HTMLElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);

  const phase = stagePhase({ asked, answer, sources, sourcesFailed, problem: problem !== null });
  const parts = answer ? revealParts(answer, sources, sourcesFailed) : [];
  const started = whole || reveal?.turn === turn; // the reveal has begun, or there is none to wait for
  const shown = whole ? Infinity : phase === "done" && started ? step : 0;
  const view = stageView(whole ? "done" : phase === "done" && !started ? "reading" : phase, {
    step: whole ? Infinity : step,
    parts: parts.length,
    pull: reveal?.pull ?? false,
    leaving,
  });
  const answering = view === "reading" || view === "pulling" || view === "revealing"; // the field hides
  // Kept between renders, so the moving stage re-plots only when the sources change; it gets them from the pull on.
  const cited = useMemo(() => (answer && sources ? citedThings(answer, sources) : []), [answer, sources]);

  // Leaving Ask, through a header link, stops its answer stream and its sources lookup.
  useEffect(
    () => () => {
      running.current?.abort();
      timers.current.forEach(clearTimeout);
    },
    [],
  );
  // In the browser only, so the times read in its time zone and the server renders no list.
  useEffect(() => void loadRecent(), []);
  // A recent question's answer takes the focus once it is on screen, as Back to the answer does.
  useEffect(() => {
    if (!answer || !focusAnswer.current) return;
    focusAnswer.current = false;
    document.getElementById("answer-text")?.focus();
  }, [answer]);

  /** Whether the sequence plays: a desktop that allows motion, a visible tab, and the stage in view. */
  function motionOk(): boolean {
    const element = stage.current;
    if (!element || document.visibilityState !== "visible" || !matchMedia(DESKTOP).matches) return false;
    const { top, bottom, height } = element.getBoundingClientRect();
    return Math.min(bottom, innerHeight) - Math.max(top, 0) >= Math.min(height, innerHeight) * 0.1;
  }

  /** Every part at once, and the status line says so: where there is no motion. */
  function showWhole(done: Answer) {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    setReveal((current) => (current ? { ...current, moving: false } : current));
    setStep(Infinity);
    setStatus(readyLine(done, storedAt, sourcesFailed));
  }

  // The checked answer and its sources are in: the pull, then the parts a step apart; or all at once.
  const dataIn = !whole && phase === "done" && answer ? turn : -1;
  useEffect(() => {
    if (dataIn < 0 || !answer) return;
    const moving = motionOk();
    const pull = moving && cited.length > 0 && stage.current?.dataset.live === "on";
    setReveal({ turn: dataIn, pull, moving });
    if (!moving) return showWhole(answer);
    setStep(0);
    const ready = readyLine(answer, storedAt, sourcesFailed);
    timers.current = revealTimes(parts.length, pull).map((at, i, all) =>
      window.setTimeout(() => {
        setStep(i + 1);
        if (i === all.length - 1) setStatus(ready);
      }, at),
    );
    // Once per answer: its data coming in starts it, and a new question's turn clears it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataIn]);

  // A new card: the focus moves to its question (the field that had it hides), the stage's top comes into view,
  // and the question flies there from the field.
  useLayoutEffect(() => {
    const sent = stage.current?.querySelector<HTMLElement>(".story-sent");
    if (!sent || whole) return; // a recent question's answer takes the focus instead
    sent.focus({ preventScroll: true });
    const from = flyFrom.current;
    flyFrom.current = null;
    const moving = motionOk();
    if (stage.current!.getBoundingClientRect().top < 0) stage.current!.scrollIntoView({ block: "start", behavior: moving ? "smooth" : "auto" });
    const bubble = sent.firstElementChild;
    if (!from || !moving || !bubble) return;
    const to = onPage(bubble);
    bubble.animate([{ transform: `translate(${from.x - to.x}px, ${from.y - to.y}px)` }, { transform: "none" }], {
      duration: FLY_MS,
      easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turn]);

  // Each part grows the card to take it, from wherever the last one left it, and shows as the card's edge passes;
  // the moving stage's membrane follows the card's box, so it grows with it. All at once where the reveal is.
  useLayoutEffect(() => {
    const card = stage.current?.querySelector<HTMLElement>(".answer-card");
    if (!card) return void (cardHeight.current = 0);
    const growing = card.getAnimations().find((animation) => animation.id === "grow");
    const from = growing ? card.getBoundingClientRect().height : cardHeight.current;
    growing?.cancel();
    const to = card.getBoundingClientRect().height;
    cardHeight.current = to;
    if (!reveal?.moving || !from || to <= from) return;
    card.animate([{ height: `${from}px`, clipPath: "inset(0)" }, { height: `${to}px`, clipPath: "inset(0)" }], {
      duration: ENTER_MS,
      easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      id: "grow",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [turn, shown]);

  /** This sign-in's recent questions. Any failure but a 401 hides the list, an API without them included. */
  async function loadRecent() {
    try {
      const found = await fetch("/api/recent");
      if (found.status === 401) return window.location.assign(SIGN_IN);
      setRecent(found.ok ? ((await found.json()) as { items: RecentAnswer[] }).items : []);
    } catch {
      setRecent([]);
    }
  }

  function fail(failure: Notice) {
    setProblem(failure);
    setStatus(failure.text);
  }

  /** The cited chunks and facts. A failure keeps the answer and adds a note; it never throws. An answer already
      whole on screen (`now`) says so in the status line at once; a revealed one says it when the reveal ends. */
  async function showSources(done: Answer, signal: AbortSignal, now: boolean) {
    const chunkIds = done.citations.flatMap((c) => (c.chunk_id ? [c.chunk_id] : []));
    const factIds = done.citations.flatMap((c) => (c.fact_id ? [c.fact_id] : []));
    if (!chunkIds.length && !factIds.length) return;
    try {
      const found = await fetch("/api/sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chunkIds, factIds }),
        signal: AbortSignal.any([signal, AbortSignal.timeout(SOURCES_TIMEOUT_MS)]),
      });
      if (found.status === 401) return window.location.assign(SIGN_IN);
      if (found.ok) return setSources((await found.json()) as Sources);
    } catch {
      if (signal.aborted) return;
    }
    setSourcesFailed(true);
    if (now) setStatus((line) => `${line} Sources could not be loaded.`);
  }

  /** Asks through the BFF; `fresh` (Ask again) answers anew instead of giving back the earlier answer. The request
      starts at once; where motion is allowed the answer on screen first clears (the leave), then the new card shows. */
  async function run(question: string, fresh = false) {
    running.current?.abort(); // a new question stops the one before
    timers.current.forEach(clearTimeout);
    const controller = new AbortController();
    running.current = controller;
    const { signal } = controller;
    const leave = answer !== null && motionOk();
    setBusy(true);
    setStatus("Answering.");
    if (leave) setLeaving(true);
    const sentAt = performance.now();
    let firstWordsMs: number | undefined;
    const reply = fetch("/api/answers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, fresh }),
      signal,
    });
    reply.catch(() => {}); // read below, after the leave
    if (leave) await wait(LEAVE_MS);
    if (signal.aborted) return;
    // The new question's card: the field clears and hides, and the question takes the top of the stage.
    form.current?.reset();
    setLeaving(false);
    setTurn((n) => n + 1);
    setAsked(question);
    setAnswer(null);
    setStoredAt(null);
    setWhole(false);
    setSources(undefined);
    setSourcesFailed(false);
    setProblem(null);
    setTiming(null);
    setReveal(null);
    setStep(0);
    try {
      const response = await reply;
      if (response.status === 401) return window.location.assign(SIGN_IN);
      if (!response.ok || !response.body) {
        return fail(notice(response.status, await response.json().catch(() => ({}))));
      }
      const result = await readEvents(response.body, () => {
        firstWordsMs ??= performance.now() - sentAt;
      });
      if (!result.answer) return fail({ text: result.failed ?? "The answer stopped before it finished." });
      const done = result.answer;
      setAnswer(done);
      setStoredAt(result.storedAt ?? null);
      if (!result.storedAt) setTiming({ firstWordsMs, completeMs: performance.now() - sentAt });
      if (!result.storedAt && !done.refused) void loadRecent(); // the API has just kept it
      await showSources(done, signal, false);
    } catch {
      // Only the stream lands here, since showSources keeps its own failures; an abort shows nothing.
      if (!signal.aborted) fail({ text: "The web server could not be reached.", demo: true });
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  /** The question flies from the field to the card's bubble; the field keeps it until the card on screen clears. */
  function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const question = String(new FormData(event.currentTarget).get("question") ?? "").trim();
    flyFrom.current = box.current ? onPage(box.current) : null;
    void run(question);
  }

  /** A recent question: its stored answer whole, with its reading, number checks and sources, and no model call. */
  function pick(item: RecentAnswer) {
    running.current?.abort(); // a sources lookup still running stops
    timers.current.forEach(clearTimeout);
    const controller = new AbortController();
    running.current = controller;
    setLeaving(false);
    setTurn((n) => n + 1);
    setAsked(item.question);
    setWhole(true);
    setProblem(null);
    setTiming(null);
    setSources(undefined);
    setSourcesFailed(false);
    setAnswer(item.answer);
    setStoredAt(item.answered_at);
    setReveal(null);
    setStep(Infinity);
    setStatus(readyLine(item.answer, item.answered_at, false));
    focusAnswer.current = true;
    void showSources(item.answer, controller.signal, true);
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

  /** Back to the empty stage, the field at its top with the focus; the card clears first where motion is allowed. */
  async function startOver() {
    running.current?.abort(); // a sources lookup still running stops
    const controller = new AbortController();
    running.current = controller;
    if (answer !== null && motionOk()) {
      setLeaving(true);
      await wait(LEAVE_MS);
      if (controller.signal.aborted) return; // a new question or a recent one came first
    }
    flushSync(() => {
      setBusy(false); // an aborted question leaves busy alone, so it is cleared here
      setLeaving(false);
      setAnswer(null);
      setAsked(null);
      setStoredAt(null);
      setWhole(false);
      setSources(undefined);
      setSourcesFailed(false);
      setProblem(null);
      setTiming(null);
      setReveal(null);
      setStep(Infinity);
      setStatus("");
    });
    form.current?.reset();
    box.current?.focus();
  }

  // The question on screen is left out of the list: by its words, or by its stored time for a repeat.
  const others = recent.filter((item) => item.question !== asked && item.answered_at !== storedAt);
  // Sources once the answer is whole on screen, so the keyboard never reaches them before it.
  const sourcesShown = answer !== null && answer.citations.length > 0 && !answering;

  // The DOM order is the reading order: the card, the status line, the field (at the top while there is no card),
  // the examples, then Recent questions and Sources.
  return (
    <div className="ask">
      <section ref={stage} className="stage" aria-label="Ask about the filings" data-phase={view} data-step={Math.min(shown, parts.length)} data-motion="still">
        <div className="stage-field" aria-hidden="true" />
        <div className="stage-layer" aria-hidden="true" />
        {/* Empty until a question, and then out of the way: the moving stage measures itself round it. */}
        <div className="stage-panel">
          {asked !== null && (
            <AnswerCard
              key={turn}
              question={asked}
              answer={answer}
              sources={sources}
              sourcesFailed={sourcesFailed}
              shown={shown}
              leaving={leaving}
              still={whole || !reveal?.moving}
              waiting={
                <div className="card-reading" data-testid="reading">
                  <p className="story-row" data-tone="reading">
                    <Glyph d={GLYPHS.read} />
                    <span>Reading the filings…</span>
                  </p>
                  {/* What FilingLens covers, none of it claimed; the moving stage floats these instead. */}
                  {covered.length > 0 && (
                    <ul className="stage-covered" aria-label="Filings FilingLens covers">
                      {covered.map((thing) => (
                        <li key={thing.filing}>{thing.filing}</li>
                      ))}
                    </ul>
                  )}
                </div>
              }
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
                    <button type="button" className="secondary small" onClick={() => void startOver()}>
                      New question
                    </button>
                  </>
                )
              }
            />
          )}
        </div>
        <p role="status" className="status" data-testid="ask-status">
          {status}
        </p>
        <form ref={form} onSubmit={ask} className="stage-ask" hidden={answering}>
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
              <span className="visually-hidden">Ask</span>
            </button>
          </div>
          <p id="question-help" className="help">
            About the tracked companies&apos; filings: 3 to 1,000 characters. Enter sends; Shift+Enter starts a new line.
          </p>
        </form>
        {view === "empty" && samples.length > 0 && (
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
        <StageMotion phase={view} covered={covered} cited={view === "reading" || view === "empty" ? [] : cited} />
      </section>
      {(others.length > 0 || sourcesShown) && (
        <div className="ask-below">
          {others.length > 0 && (
            <div className="ask-card ask-recent" data-testid="recent-card">
              <RecentQuestions items={others} busy={busy} onPick={pick} />
            </div>
          )}
          {sourcesShown && (
            <div className="ask-card ask-sources" data-testid="sources-card">
              <SourceList answer={answer} sources={sources} sourcesFailed={sourcesFailed} />
            </div>
          )}
        </div>
      )}
      <QuoteInView />
    </div>
  );
}

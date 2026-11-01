"use client";
// Ask: streams a draft through the BFF, then shows the validated answer and its sources, and this
// sign-in's recent questions, whose stored answers come back without a model call.
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

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
import { AnswerMain, ReadAs, SourceList, sourceLabel } from "./answer-view.tsx";
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

/** `samples`: questions the filings can answer, offered under the empty box; a click only fills it. */
export function Ask({ samples }: { samples: string[] }) {
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

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    await run(String(new FormData(event.currentTarget).get("question") ?? "").trim());
  }

  /** A recent question: its stored answer with its reading, number checks and sources, and no model call. */
  function pick(item: RecentAnswer) {
    running.current?.abort(); // a sources lookup still running stops
    const controller = new AbortController();
    running.current = controller;
    if (box.current) box.current.value = item.question;
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

  /** Back to an empty question box, with the focus in it; a sources lookup still running stops. */
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

  // From 64rem the sources panel sits beside the whole column; the DOM order is the reading order.
  return (
    <div className="ask">
      <div className="ask-main">
        <form ref={form} onSubmit={ask} className="stack ask-form">
          <label htmlFor="question">Your question</label>
          <textarea ref={box} id="question" name="question" rows={3} required minLength={3} maxLength={1000} aria-describedby="question-help" />
          <p id="question-help" className="help">
            About the tracked companies&apos; filings, such as &ldquo;What was Apple&apos;s total revenue in fiscal
            2025?&rdquo; 3 to 1,000 characters.
          </p>
          {/* aria-disabled, not disabled: a disabled button would drop the keyboard user's focus */}
          <button type="submit" aria-disabled={busy || undefined}>
            {busy ? "Answering…" : "Ask"}
          </button>
        </form>
        {samples.length > 0 && !answer && draft === null && (
          <section className="samples" aria-labelledby="samples-title" data-testid="samples">
            <h2 id="samples-title">Try a question the filings can answer</h2>
            <ul>
              {samples.map((sample) => (
                <li key={sample}>
                  <button
                    type="button"
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
        {problem && (
          <div className="problem" data-testid="ask-error">
            <p>{problem.text}</p>
            {problem.demo && (
              <p>
                <Link href="/demo">See the saved answers</Link>
              </p>
            )}
          </div>
        )}
        {draft !== null && (
          <section className="draft" aria-busy="true" aria-labelledby="draft-title" data-testid="draft">
            <h2 id="draft-title">
              Draft <span className="tag">citations not checked yet</span>
            </h2>
            <p>{draft}</p>
          </section>
        )}
        {answer && <ReadAs reading={answer.reading} />}
        {answer && (
          <section className="result" aria-labelledby="answer-title" data-testid="answer">
            <div className="result-head">
              <h2 id="answer-title">Answer</h2>
              {storedAt ? (
                <p className="timings" data-testid="stored">
                  {storedLine(storedAt)}
                </p>
              ) : (
                timing && (
                  <p className="timings" data-testid="timings">
                    {timingLine(timing.firstWordsMs, timing.completeMs, answer.citations.length, answer.checks.length > 0)}
                  </p>
                )
              )}
            </div>
            <AnswerMain answer={answer} sources={sources} />
            <div className="actions">
              {answer.citations.length > 0 && (
                <button type="button" onClick={() => copy(answer)}>
                  Copy answer with sources
                </button>
              )}
              {storedAt && asked && (
                <button type="button" aria-disabled={busy || undefined} onClick={() => !busy && run(asked, true)}>
                  Ask again
                </button>
              )}
              <button type="button" onClick={startOver}>
                New question
              </button>
            </div>
          </section>
        )}
        <RecentQuestions items={others} busy={busy} onPick={pick} />
      </div>
      {answer && <SourceList answer={answer} sources={sources} sourcesFailed={sourcesFailed} />}
      <QuoteInView />
    </div>
  );
}

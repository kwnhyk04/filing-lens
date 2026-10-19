"use client";
// Ask: streams a draft through the BFF, then shows the validated answer and its sources.
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { createSseParser, type Answer, type AnswerEvent } from "../lib/answer.ts";
import type { Sources } from "../lib/demo.ts";
import { AnswerMain, SourceList } from "./answer-view.tsx";
import { QuoteInView } from "./quote-in-view.tsx";

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

/** Reads the event stream; deltas go to `onDelta` as they arrive. */
async function readEvents(body: ReadableStream<Uint8Array>, onDelta: (text: string) => void) {
  const result: { answer?: Answer; failed?: string } = {};
  const push = createSseParser((data) => {
    const event = JSON.parse(data) as AnswerEvent;
    if (event.type === "delta") onDelta(event.text);
    else if (event.type === "completed") result.answer = event.answer;
    else result.failed = event.problem.detail ?? "The answer failed.";
  });
  const decoder = new TextDecoder();
  const reader = body.getReader();
  for (let read = await reader.read(); !read.done; read = await reader.read()) {
    push(decoder.decode(read.value, { stream: true }));
  }
  return result;
}

export function Ask() {
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<string | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [sources, setSources] = useState<Sources>();
  const [sourcesFailed, setSourcesFailed] = useState(false);
  const [problem, setProblem] = useState<Notice | null>(null);
  const [status, setStatus] = useState("");
  const running = useRef<AbortController | null>(null);

  // Leaving Ask, through a header link, stops its answer stream and its sources lookup.
  useEffect(() => () => running.current?.abort(), []);

  function fail(failure: Notice) {
    setDraft(null);
    setProblem(failure);
    setStatus(failure.text);
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

  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const question = String(new FormData(event.currentTarget).get("question") ?? "").trim();
    running.current?.abort(); // a new question stops the one before
    const controller = new AbortController();
    running.current = controller;
    const { signal } = controller;
    setBusy(true);
    setDraft("");
    setAnswer(null);
    setSources(undefined);
    setSourcesFailed(false);
    setProblem(null);
    setStatus("Answering.");
    try {
      const response = await fetch("/api/answers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
        signal,
      });
      if (response.status === 401) return window.location.assign("/login?next=/");
      if (!response.ok || !response.body) {
        return fail(notice(response.status, await response.json().catch(() => ({}))));
      }
      const result = await readEvents(response.body, (text) => setDraft((sofar) => (sofar ?? "") + text));
      if (!result.answer) return fail({ text: result.failed ?? "The answer stopped before it finished." });
      const done = result.answer;
      setDraft(null);
      setAnswer(done);
      const count = done.citations.length;
      setStatus(done.refused ? "Not answered; the reason is below." : `Answer ready, with ${count} source${count === 1 ? "" : "s"}.`);
      await showSources(done, signal);
    } catch {
      // Only the stream lands here, since showSources keeps its own failures; an abort shows nothing.
      if (!signal.aborted) fail({ text: "The web server could not be reached.", demo: true });
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  // From 64rem the sources panel sits beside the whole column; the DOM order is the reading order.
  return (
    <div className="ask">
      <div className="ask-main">
        <form onSubmit={ask} className="stack ask-form">
          <label htmlFor="question">Your question</label>
          <textarea id="question" name="question" rows={3} required minLength={3} maxLength={1000} aria-describedby="question-help" />
          <p id="question-help" className="help">
            About the tracked companies&apos; filings, such as &ldquo;What was Apple&apos;s total revenue in fiscal
            2025?&rdquo; 3 to 1,000 characters.
          </p>
          {/* aria-disabled, not disabled: a disabled button would drop the keyboard user's focus */}
          <button type="submit" aria-disabled={busy || undefined}>
            {busy ? "Answering…" : "Ask"}
          </button>
        </form>
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
        {answer && (
          <section className="result" aria-labelledby="answer-title" data-testid="answer">
            <h2 id="answer-title">Answer</h2>
            <AnswerMain answer={answer} sources={sources} />
          </section>
        )}
      </div>
      {answer && <SourceList answer={answer} sources={sources} sourcesFailed={sourcesFailed} />}
      <QuoteInView />
    </div>
  );
}

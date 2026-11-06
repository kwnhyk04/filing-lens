"use client";
// The landing's moving hero, on the engine after Prompt Bond (bond.tsx): it tells the still's story
// (story-panel.tsx), then the loop's other saved answers, each held 7 s before the next, round and round, and
// loads only on a desktop once the page has loaded (hero-motion.tsx). It stops for reduced motion, a hidden tab, a
// hero scrolled away, the pointer or keyboard focus on the card, and the Pause button. The floating things drift on
// by CSS alone while an answer holds and under the pointer; the others stop them too.
import { animate } from "motion";
import * as React from "react";
import { createPortal } from "react-dom";

import { demo } from "../lib/demo.ts";
import { SLOTS } from "../lib/stage.ts";
import { heroStories, type HeroStory, storyBeats } from "../lib/story.ts";
import { FieldBoundary, type FieldProps, Icon, LAST, Story, type Thing, useMode, useMotionVisibility } from "./bond.tsx";
import "./hero-live.css";

/* ── The cue: each word rises out of a soft blur, once per new line. While the loop turns, screen readers are
 * not told each cue (aria-live off, as in WAI-ARIA's carousel pattern); paused, they are. ── */

function TextReveal({ text, moving }: { text: string; moving: boolean }) {
  const host = React.useRef<HTMLParagraphElement>(null);
  const played = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!host.current || played.current === text) return;
    played.current = text;
    if (!moving) return;
    const words = Array.from(host.current.querySelectorAll<HTMLElement>("[data-reveal]"));
    const step = Math.min(0.024, 0.6 / Math.max(1, words.length - 1));
    const controls = animate(
      words,
      { "--reveal-opacity": [0, 1], "--reveal-y": ["0.28em", "0em"], "--reveal-blur": ["5px", "0px"] },
      { duration: 0.44, delay: (i) => i * step, ease: [0.2, 0.65, 0.25, 1] },
    );
    return () => {
      controls.stop();
      for (const word of words) for (const name of ["--reveal-opacity", "--reveal-y", "--reveal-blur"]) word.style.removeProperty(name);
    };
  }, [text, moving]);
  return (
    <p ref={host} className="pb-cue" aria-live={moving ? "off" : "polite"} aria-atomic="true">
      <span className="visually-hidden">{text}</span>
      <span aria-hidden="true">
        {text.split(/(\s+)/).map((word, i) =>
          /^\s*$/.test(word) ? (
            word
          ) : (
            <span key={`${text}-${i}`} data-reveal="">
              {word}
            </span>
          ),
        )}
      </span>
    </p>
  );
}

/* ── The stories: each saved answer's question, sources, answer and check, told in turn ── */

/** One story's rows, beats and things. What floats round the panel: its cited sources first, one on each side
    (a passage by its item, a fact by its value), then the snapshot's other filings. */
function plotOf(story: HeroStory) {
  const passages = story.passages.length;
  const cited = story.passages.map((p): Thing =>
    p.kind === "passage"
      ? { kind: "passage", title: `Item ${p.item}`, sub: p.filing, icon: "file-text" }
      : { kind: "fact", title: p.quote, sub: p.filing, icon: "hash" },
  );
  const filings = story.others.slice(0, SLOTS - passages - 1).map((filing): Thing => {
    const [ticker, form, year] = filing.split(" ");
    return { kind: "filing", title: `${ticker} ${form}`, sub: year, icon: "file" };
  });
  return {
    story,
    env: [...cited, ...filings, ...Array<null>(SLOTS - cited.length - filings.length).fill(null)],
    pulls: cited.map((_, i) => i), // each cited source onto its row, after the question and the reading
    first: 2,
    rows: passages + 4, // the question, the reading, each source, the answer, the check
    reply: 2 + passages,
    check: 3 + passages,
    beats: storyBeats(story),
  };
}
const PLOTS = heroStories(demo).map(plotOf);

/** Whether the pointer or keyboard focus is on the story's card, which pauses the loop until it leaves. Watched
    on the figure, which stays while each answer's card takes the last one's place. */
function useHeld(hero: HTMLElement | null) {
  const [held, setHeld] = React.useState(false);
  React.useEffect(() => {
    const figure = hero?.querySelector<HTMLElement>(".hero-story");
    if (!figure) return;
    let pointer = false, focus = false;
    const onCard = (node: EventTarget | null) => node instanceof Element && node.closest(".story-live") !== null;
    const update = () => setHeld(pointer || focus);
    const over = (event: PointerEvent) => { pointer = onCard(event.target); update(); };
    const out = (event: PointerEvent) => { if (!onCard(event.relatedTarget)) { pointer = false; update(); } };
    const focusIn = (event: FocusEvent) => { focus = onCard(event.target); update(); };
    const focusOut = (event: FocusEvent) => { if (!onCard(event.relatedTarget)) { focus = false; update(); } };
    figure.addEventListener("pointerover", over);
    figure.addEventListener("pointerout", out);
    figure.addEventListener("focusin", focusIn);
    figure.addEventListener("focusout", focusOut);
    return () => {
      figure.removeEventListener("pointerover", over);
      figure.removeEventListener("pointerout", out);
      figure.removeEventListener("focusin", focusIn);
      figure.removeEventListener("focusout", focusOut);
    };
  }, [hero]);
  return held;
}

/** Each letter of the headline grows heavier as the pointer comes near: a smoothstep over 160 px. */
function useProximity(hero: HTMLElement | null, moving: boolean) {
  React.useEffect(() => {
    if (!hero) return;
    const letters = Array.from(hero.querySelectorAll<HTMLElement>(".hero-word > span"));
    const weights = letters.map((letter) => (letter.closest(".hero-line-1") ? [650, 780] : [380, 620]));
    const reset = () => letters.forEach((letter) => letter.style.removeProperty("font-variation-settings"));
    if (!moving || !matchMedia("(hover: hover) and (pointer: fine)").matches) {
      reset();
      return;
    }
    let raf = 0;
    const move = (event: PointerEvent) => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        letters.forEach((letter, i) => {
          const r = letter.getBoundingClientRect();
          const p = 1 - Math.min(1, Math.hypot(event.clientX - r.x - r.width / 2, event.clientY - r.y - r.height / 2) / 160);
          const [from, to] = weights[i];
          letter.style.setProperty("font-variation-settings", `"wght" ${Math.round(from + (to - from) * p * p * (3 - 2 * p))}`);
        });
      });
    };
    hero.addEventListener("pointermove", move);
    hero.addEventListener("pointerleave", reset);
    return () => {
      cancelAnimationFrame(raf);
      hero.removeEventListener("pointermove", move);
      hero.removeEventListener("pointerleave", reset);
      reset();
    };
  }, [hero, moving]);
}

/* ── The moving hero: finds its places in the still hero, tells the stories in turn, then brings in the field ── */

export function HeroLive() {
  const anchor = React.useRef<HTMLSpanElement>(null), live = React.useRef(false);
  const [hero, setHero] = React.useState<HTMLElement | null>(null);
  const [Field, setField] = React.useState<React.ComponentType<FieldProps> | null>(null);
  const [paused, setPaused] = React.useState(false);
  const [told, setTold] = React.useState({ index: 0, replay: 0 }); // which answer, and its play-through
  const [beat, setBeat] = React.useState(0);
  const [idle, setIdle] = React.useState(false); // an answer holds: nothing to play but the things' drift
  const mode = useMode();
  const { enabled, inView } = useMotionVisibility(hero);
  const held = useHeld(hero);
  const drift = enabled && inView && !paused;
  const moving = drift && !held;
  const plot = PLOTS[told.index];
  // What the floating things keep clear of: the headline and the lead.
  const heads = React.useMemo(
    () => [hero?.querySelector(".hero-title"), hero?.querySelector(".hero-lead")].filter((el): el is Element => el != null),
    [hero],
  );

  React.useLayoutEffect(() => {
    setHero(anchor.current?.closest<HTMLElement>(".hero") ?? null);
  }, []);
  useProximity(hero, moving);

  // After the last answer, the first again; Replay tells the current one again.
  const next = React.useCallback(() => {
    setBeat(0);
    setTold(({ index, replay }) => ({ index: (index + 1) % PLOTS.length, replay }));
  }, []);
  const again = () => {
    setBeat(0);
    setTold(({ index, replay }) => ({ index, replay: replay + 1 }));
  };

  const onReady = React.useCallback(() => {
    if (!hero || live.current) return;
    live.current = true;
    hero.dataset.live = "on";
    const still = hero.querySelector<HTMLElement>(".story-still");
    if (still) {
      still.setAttribute("aria-hidden", "true");
      still.inert = true;
    }
    // The field's three.js comes last, once the story already runs.
    import("./hero-field.tsx").then((module) => setField(() => module.default));
  }, [hero]);

  const field = hero?.querySelector<HTMLElement>(".hero-field");
  const stage = hero?.querySelector<HTMLElement>(".hero-stage");
  const bar = (
    <div className="pb-controls">
      <button type="button" className="pb-control" onClick={again}>
        <Icon name="replay" />
        Replay
      </button>
      <button type="button" className="pb-control" aria-pressed={paused} onClick={() => setPaused((v) => !v)}>
        <Icon name={paused ? "play" : "pause"} />
        <span className="visually-hidden">{paused ? "Resume motion" : "Pause motion"}</span>
      </button>
    </div>
  );
  return (
    <>
      <span ref={anchor} hidden />
      {hero && stage && (
        <>
          <Story
            key={`${told.index}-${told.replay}`}
            plot={plot}
            host={hero}
            layer={stage}
            heads={heads}
            moving={moving}
            drift={drift}
            quiet={!enabled}
            mode={mode}
            onReady={onReady}
            onBeat={setBeat}
            onDone={next}
            onIdle={setIdle}
          />
          {/* The caption and its controls stay while the answers change, so focus on Pause or Replay stays. */}
          <div className="story-caption">
            <TextReveal text={plot.beats[beat].cue} moving={moving} />
            <div className="pb-progress" role="img" aria-label={`Story: ${plot.beats[beat].label}`}>
              {plot.beats.slice(1, LAST).map((b, i) => (
                <span key={b.label} data-complete={beat > i + 1} data-current={beat === i + 1} />
              ))}
            </div>
            {bar}
          </div>
        </>
      )}
      {Field && field &&
        createPortal(
          <FieldBoundary>
            <Field mode={mode} moving={moving && !idle} />
          </FieldBoundary>,
          field,
        )}
    </>
  );
}

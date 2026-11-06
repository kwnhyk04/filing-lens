"use client";
// Ask's moving stage: the landing hero's engine (bond.tsx) playing the page's sequence round Ask's own field and card.
// While FilingLens reads, the membrane gathers round the card and covers it, the covered filings floating, none
// claimed. Once the checked answer and its sources are in, it reaches each cited filing, left and right, and draws it
// against the card while the page reveals the parts, growing with the card as each comes. About a second after the
// card has settled it lets them go, and they drift home. The membrane and the field move only while there is something
// to play. At rest no frame runs, and the floating things drift on by CSS alone, on the compositor, until a hidden tab
// or a stage scrolled away stops them, or Pause in the stage's corner, the hero's button, for as long as the session
// lasts (WCAG 2.2.2). An answer still plays while paused. Loaded on a desktop once the page has loaded (hero-motion.tsx).
import * as React from "react";
import { createPortal } from "react-dom";

import { placeThings, type StageProps, type View } from "../lib/stage.ts";
import { FIND, FieldBoundary, type FieldProps, GATHER, Icon, LAST, type Page, PULLS, RELEASE, Story, useMode, useMotionVisibility } from "./bond.tsx";

const NONE: Element[] = []; // the stage has no headline for the things to keep clear of
const PAUSED = "filinglens.ask-drift-paused"; // in sessionStorage; with storage refused, Pause lasts as long as the page

function pausedBefore() {
  try {
    return sessionStorage.getItem(PAUSED) === "1";
  } catch {
    return false;
  }
}

function remember(paused: boolean) {
  try {
    sessionStorage.setItem(PAUSED, paused ? "1" : "0");
  } catch {
    // The choice still holds on this page.
  }
}

/** Each of the stage's views as the engine's beat: rest, gather, pull, settle round the answer, or let go. */
const BEATS: Record<View, number> = { empty: 0, reading: GATHER, pulling: FIND, revealing: LAST, done: LAST, failed: LAST, leaving: RELEASE };
/** Nothing in play: the engine lets an answer's sources go, then the stage comes to rest. */
const REST = new Set<View>(["empty", "done", "failed"]);

export function AskLive({ phase, covered, cited }: StageProps) {
  const anchor = React.useRef<HTMLSpanElement>(null);
  const [stage, setStage] = React.useState<HTMLElement | null>(null);
  const [Field, setField] = React.useState<React.ComponentType<FieldProps> | null>(null);
  const [idle, setIdle] = React.useState(false); // nothing to play but the filings' drift
  const [paused, setPaused] = React.useState(pausedBefore); // this file loads in the browser only
  const mode = useMode();
  const { enabled, inView } = useMotionVisibility(stage);
  const moving = enabled && inView;

  React.useLayoutEffect(() => {
    setStage(anchor.current?.closest<HTMLElement>(".stage") ?? null);
  }, []);

  // Each cited source in its own filing's place, at most as many as the membrane can pull in. The card has no rows
  // for the engine: the page shows its parts, and each pull ends at the card's edge.
  const plot = React.useMemo(() => {
    const { env, pulls } = placeThings(covered, cited.slice(0, PULLS));
    return { env, pulls, first: 0, rows: 0, reply: 0, check: 0 };
  }, [covered, cited]);
  // The field and the card stay in the DOM for the page's life (the field is hidden, never removed), so these hold.
  const page = React.useMemo((): Page | null => {
    const capsule = stage?.querySelector<HTMLElement>(".stage-input"), panel = stage?.querySelector<HTMLElement>(".stage-panel");
    return capsule && panel ? { capsule, panel } : null;
  }, [stage]);
  const layer = stage?.querySelector<HTMLElement>(".stage-layer");
  const field = stage?.querySelector<HTMLElement>(".stage-field");

  const onReady = React.useCallback(() => {
    if (!stage) return;
    stage.dataset.live = "on";
    // The field's three.js comes last, once the stage already plays.
    import("./hero-field.tsx").then((module) => setField(() => module.default));
  }, [stage]);

  return (
    <>
      <span ref={anchor} hidden />
      {stage && page && layer && (
        <Story plot={plot} host={stage} layer={layer} heads={NONE} page={page} target={BEATS[phase]} rest={REST.has(phase)} moving={moving} drift={moving && !paused} quiet={!enabled} mode={mode} onReady={onReady} onIdle={setIdle} />
      )}
      {/* Last in the stage, so the keyboard reaches the card and the field first. */}
      <div className="pb-controls">
        <button
          type="button"
          className="pb-control"
          aria-pressed={paused}
          onClick={() => {
            remember(!paused);
            setPaused(!paused);
          }}
        >
          <Icon name={paused ? "play" : "pause"} />
          <span className="visually-hidden">{paused ? "Resume motion" : "Pause motion"}</span>
        </button>
      </div>
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

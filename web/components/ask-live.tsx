"use client";
// Ask's moving stage: the landing hero's engine (bond.tsx) playing the page's sequence round Ask's own field and card.
// While FilingLens reads, the membrane gathers round the card and covers it, the covered filings floating, none
// claimed. Once the checked answer and its sources are in, it reaches each cited filing, left and right, and draws it
// against the card while the page reveals the parts; it holds them until the answer leaves, then lets go. Loaded on a
// desktop once the page has loaded (hero-motion.tsx); it moves only while there is something to play.
import * as React from "react";
import { createPortal } from "react-dom";

import { placeThings, type StageProps, type View } from "../lib/stage.ts";
import { FIND, FieldBoundary, type FieldProps, GATHER, Icon, LAST, type Page, PULLS, RELEASE, Story, useMode, useMotionVisibility } from "./bond.tsx";

const NONE: Element[] = []; // the stage has no headline for the things to keep clear of
/** Each of the stage's views as the engine's beat: rest, gather, pull, settle round the answer, or let go. */
const BEATS: Record<View, number> = { empty: 0, reading: GATHER, pulling: FIND, revealing: LAST, done: LAST, failed: LAST, leaving: RELEASE };

export function AskLive({ phase, turn, covered, cited, paused, onPause }: StageProps) {
  const anchor = React.useRef<HTMLSpanElement>(null);
  const [stage, setStage] = React.useState<HTMLElement | null>(null);
  const [Field, setField] = React.useState<React.ComponentType<FieldProps> | null>(null);
  const [rested, setRested] = React.useState<string | null>(null); // the question and view whose beat has played
  const mode = useMode();
  const { enabled, inView } = useMotionVisibility(stage);

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

  // Motion until each view's beat has played; still at rest, round a finished answer and round an error.
  const key = `${turn}:${phase}`;
  const settles = phase === "empty" || phase === "done" || phase === "failed";
  const moving = enabled && inView && !paused && !(settles && rested === key);
  const rest = React.useCallback(() => setRested(key), [key]);

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
        <Story
          plot={plot}
          host={stage}
          layer={layer}
          heads={NONE}
          page={page}
          target={BEATS[phase]}
          moving={moving}
          quiet={!enabled}
          mode={mode}
          onReady={onReady}
          onDone={rest}
        />
      )}
      {/* After the card and the field in the DOM, so the keyboard reaches them first. */}
      <div className="pb-controls">
        <button type="button" className="pb-control" aria-pressed={paused} onClick={() => onPause(!paused)}>
          <Icon name={paused ? "play" : "pause"} />
          <span className="visually-hidden">{paused ? "Resume motion" : "Pause motion"}</span>
        </button>
      </div>
      {Field && field &&
        createPortal(
          <FieldBoundary>
            <Field mode={mode} moving={moving} />
          </FieldBoundary>,
          field,
        )}
    </>
  );
}

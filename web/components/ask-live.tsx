"use client";
// Ask's moving stage: the landing hero's engine (bond.tsx) playing a live answer's states round Ask's own field and
// card. While FilingLens reads, the organisms roam among the covered filings, none of them claimed; once the checked
// answer is in they gather round its card; once its sources load, the membrane pulls each cited source onto its
// row. The card shows each part the moment it is reported, and the membrane only catches up. Loaded on a desktop
// once the page has loaded (hero-motion.tsx); it moves only while there is something to play.
import * as React from "react";
import { createPortal } from "react-dom";

import { placeThings, type StageProps } from "../lib/stage.ts";
import { FIND, FieldBoundary, type FieldProps, GATHER, Icon, type Page, PULLS, Story, useMode, useMotionVisibility } from "./bond.tsx";

const NONE: Element[] = []; // the stage has no headline for the things to keep clear of
const FIRST = 4; // the first passage's row in the card, after the question, the reading, the reply and the check

export function AskLive({ phase, turn, covered, cited }: StageProps) {
  const anchor = React.useRef<HTMLSpanElement>(null);
  const [stage, setStage] = React.useState<HTMLElement | null>(null);
  const [Field, setField] = React.useState<React.ComponentType<FieldProps> | null>(null);
  const [paused, setPaused] = React.useState(false);
  const [rested, setRested] = React.useState<string | null>(null); // the question and phase whose pulls have played
  const mode = useMode();
  const { enabled, inView } = useMotionVisibility(stage);

  React.useLayoutEffect(() => {
    setStage(anchor.current?.closest<HTMLElement>(".stage") ?? null);
  }, []);

  // Each cited source in its own filing's place, at most as many as the membrane can pull in.
  const plot = React.useMemo(() => {
    const { env, pulls } = placeThings(covered, cited.slice(0, PULLS));
    return { env, pulls, first: FIRST, rows: FIRST + pulls.length, reply: 2, check: 3 };
  }, [covered, cited]);
  const page = React.useMemo((): Page | null => {
    const capsule = stage?.querySelector<HTMLElement>(".stage-input"), panel = stage?.querySelector<HTMLElement>(".stage-panel");
    return capsule && panel ? { capsule, panel } : null;
  }, [stage]);
  const layer = stage?.querySelector<HTMLElement>(".stage-layer");
  const field = stage?.querySelector<HTMLElement>(".stage-field");

  // Motion while it reads, while the answer waits for its sources, and until their pulls have played; still
  // otherwise: the empty stage, an error, and a finished answer.
  const key = `${turn}:${phase}`;
  const active = phase === "reading" || phase === "answered" || (phase === "done" && rested !== key);
  const moving = enabled && inView && !paused && active;
  const target = phase === "answered" ? GATHER : phase === "done" ? FIND : 0;
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
          target={target}
          moving={moving}
          quiet={!enabled}
          mode={mode}
          onReady={onReady}
          onDone={rest}
        />
      )}
      {/* After the card in the DOM, so the keyboard reaches the field, Ask, the answer's links and its actions first. */}
      <div className="pb-controls">
        <button type="button" className="pb-control" aria-pressed={paused} onClick={() => setPaused((v) => !v)}>
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

"use client";
// Loads a moving story once the page has loaded and the browser is idle, and only on a desktop: a wide screen
// with a fine pointer, motion allowed, and WebGL on a graphics card. Everyone else keeps the calm version, and
// the page says which it got in `data-motion` ("live" or "still"). The landing's hero and Ask's stage share it.
import { type ComponentType, useEffect, useState } from "react";

import { softwareRenderer } from "../lib/motion.ts";
import type { StageProps } from "../lib/stage.ts";

/** A desktop that allows motion: where the moving stories may load, and where Ask's sequence plays. */
export const DESKTOP = "(min-width: 64rem) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)";

/** WebGL that a graphics card draws: refused when the browser reports a major performance caveat, or when
    the renderer is a software one (SwiftShader, llvmpipe, Windows' basic driver), which the flag lets by. */
function fastWebgl(): boolean {
  try {
    const gl = document.createElement("canvas").getContext("webgl", { failIfMajorPerformanceCaveat: true });
    if (!gl) return false;
    const info = gl.getExtension("WEBGL_debug_renderer_info");
    const renderer = String(gl.getParameter(info ? info.UNMASKED_RENDERER_WEBGL : gl.RENDERER));
    gl.getExtension("WEBGL_lose_context")?.loseContext(); // the probe gives its context back at once
    return !softwareRenderer(renderer);
  } catch {
    return false;
  }
}

/** The moving component, once loaded on a desktop that allows it; `host` gets `data-motion` either way. */
function useDesktopMotion<P>(host: string, load: () => Promise<ComponentType<P>>): ComponentType<P> | null {
  const [Live, setLive] = useState<ComponentType<P> | null>(null);

  useEffect(() => {
    if (!matchMedia(DESKTOP).matches) return;
    let cancelled = false;
    let idle = 0;
    let timer = 0;
    let frame = 0;
    const start = () => {
      if (cancelled) return;
      const fast = fastWebgl();
      document.querySelector<HTMLElement>(host)?.setAttribute("data-motion", fast ? "live" : "still");
      if (!fast) return;
      load().then((component) => {
        if (!cancelled) setLive(() => component);
      });
    };
    // Safari before 18.4 has no requestIdleCallback: a short timeout stands in.
    const idleSupported = typeof window.requestIdleCallback === "function";
    const whenIdle = () => {
      if (idleSupported) idle = window.requestIdleCallback(start, { timeout: 2000 });
      else timer = window.setTimeout(start, 200);
    };
    // Two frames after the load event, so the calm version is on screen before any WebGL work starts.
    const loaded = () => {
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(whenIdle);
      });
    };
    if (document.readyState === "complete") loaded();
    else window.addEventListener("load", loaded, { once: true });
    return () => {
      cancelled = true;
      window.removeEventListener("load", loaded);
      cancelAnimationFrame(frame);
      if (idleSupported) window.cancelIdleCallback(idle);
      window.clearTimeout(timer);
    };
    // The host and loader are fixed for each caller.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return Live;
}

export function HeroMotion() {
  const Live = useDesktopMotion<object>(".hero", () => import("./hero-live.tsx").then((module) => module.HeroLive));
  return Live ? <Live /> : null;
}

/** Ask's moving stage over its calm one: the same states, played by the hero's engine. */
export function StageMotion(props: StageProps) {
  const Live = useDesktopMotion<StageProps>(".stage", () => import("./ask-live.tsx").then((module) => module.AskLive));
  return Live ? <Live {...props} /> : null;
}

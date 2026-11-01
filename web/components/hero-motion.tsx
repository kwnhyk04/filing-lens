"use client";
// Loads the hero's moving story once the page has loaded and the browser is idle, and only on a desktop:
// a wide screen with a fine pointer, motion allowed, and WebGL on a graphics card. Everyone else keeps the
// still, and the hero says which it got in `data-motion` ("live" or "still").
import { type ComponentType, useEffect, useState } from "react";

import { softwareRenderer } from "../lib/motion.ts";

const DESKTOP = "(min-width: 64rem) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)";

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

export function HeroMotion() {
  const [Live, setLive] = useState<ComponentType | null>(null);

  useEffect(() => {
    if (!matchMedia(DESKTOP).matches) return;
    let cancelled = false;
    let idle = 0;
    let timer = 0;
    let frame = 0;
    const load = () => {
      if (cancelled) return;
      const fast = fastWebgl();
      document.querySelector<HTMLElement>(".hero")?.setAttribute("data-motion", fast ? "live" : "still");
      if (!fast) return;
      import("./hero-live.tsx").then((module) => {
        if (!cancelled) setLive(() => module.HeroLive);
      });
    };
    // Safari before 18.4 has no requestIdleCallback: a short timeout stands in.
    const idleSupported = typeof window.requestIdleCallback === "function";
    const whenIdle = () => {
      if (idleSupported) idle = window.requestIdleCallback(load, { timeout: 2000 });
      else timer = window.setTimeout(load, 200);
    };
    // Two frames after the load event, so the still is on screen before any WebGL work starts.
    const start = () => {
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(whenIdle);
      });
    };
    if (document.readyState === "complete") start();
    else window.addEventListener("load", start, { once: true });
    return () => {
      cancelled = true;
      window.removeEventListener("load", start);
      cancelAnimationFrame(frame);
      if (idleSupported) window.cancelIdleCallback(idle);
      window.clearTimeout(timer);
    };
  }, []);

  return Live ? <Live /> : null;
}

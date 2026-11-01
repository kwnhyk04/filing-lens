"use client";
// Loads the hero's moving story once the page has loaded and the browser is idle, and only on a desktop:
// a wide screen with a fine pointer, motion allowed, and WebGL. Everyone else keeps the still.
import { type ComponentType, useEffect, useState } from "react";

const DESKTOP = "(min-width: 64rem) and (hover: hover) and (pointer: fine) and (prefers-reduced-motion: no-preference)";

function webgl(): boolean {
  try {
    const gl = document.createElement("canvas").getContext("webgl");
    gl?.getExtension("WEBGL_lose_context")?.loseContext(); // the probe gives its context back at once
    return gl !== null;
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
      if (cancelled || !webgl()) return;
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

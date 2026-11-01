"use client";
// The moving hero, after Prompt Bond by Cojeev (21st.dev, MIT; docs/third-party.md): a living membrane grows
// round the question, reaches the two passages it needs, and settles round the answer and its check. It
// tells the still's story (story-panel.tsx) and loads only on a desktop once the page has loaded
// (hero-motion.tsx). It stops for reduced motion, a hidden tab, a hero scrolled away, and the Pause button.
import { animate, type AnimationPlaybackControls, type AnimationSequence, cancelFrame, frame } from "motion";
import * as React from "react";
import { createPortal } from "react-dom";

import { demo } from "../lib/demo.ts";
import { heroStory } from "../lib/story.ts";
import { appearance, themeOf } from "../lib/theme.ts";
import "./hero-live.css";
import { StoryPanel } from "./story-panel.tsx";

const story = heroStory(demo);
type Mode = "light" | "dark";

/* ── Motion gates: a visible tab without reduced motion, and the hero on screen ── */

function subscribePreferences(listener: () => void) {
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");
  media.addEventListener("change", listener);
  document.addEventListener("visibilitychange", listener);
  return () => {
    media.removeEventListener("change", listener);
    document.removeEventListener("visibilitychange", listener);
  };
}
const readPreferences = () =>
  document.visibilityState === "visible" && !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function useMotionVisibility(element: Element | null) {
  const enabled = React.useSyncExternalStore(subscribePreferences, readPreferences, () => false);
  const [inView, setInView] = React.useState(false);
  React.useEffect(() => {
    if (!element) return;
    const observer = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.1 });
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return { enabled, inView };
}

/** Light or dark, as the page looks: the theme picked in the header, else the system's. */
function useMode(): Mode {
  const read = () =>
    appearance(themeOf(document.documentElement.dataset.theme), matchMedia("(prefers-color-scheme: dark)").matches);
  const subscribe = (listener: () => void) => {
    const media = matchMedia("(prefers-color-scheme: dark)");
    const observer = new MutationObserver(listener);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    media.addEventListener("change", listener);
    return () => {
      observer.disconnect();
      media.removeEventListener("change", listener);
    };
  };
  return React.useSyncExternalStore(subscribe, read, () => "light");
}

/* ── Glyphs: lucide geometry (ISC licence, docs/third-party.md) ── */

const GEOMETRY: Record<string, string> = {
  file: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8ZM14 3v5h5",
  "file-text":
    "M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2zM14 2v5a1 1 0 0 0 1 1h5M10 9H8M16 13H8M16 17H8",
  play: "M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z",
  pause: "M14 3h5v18h-5zM5 3h5v18H5z",
  replay: "M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8M3 3v5h5",
  "arrow-right": "M5 12h14m-7-7 7 7-7 7",
};

function Icon({ name }: { name: string }) {
  return (
    <svg className="pb-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d={GEOMETRY[name]} />
    </svg>
  );
}

/* ── The cue: each word rises out of a soft blur, once per new line ── */

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
    <p ref={host} className="pb-cue" aria-live="polite" aria-atomic="true">
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

/* ── The membrane: signed-distance cells and strands, smooth-unioned in one WebGL pass ── */

type MembraneCell = { x: number; y: number; hw: number; hh: number; r: number; tone: number; rot?: number; w?: number };
type MembraneStrand = { ax: number; ay: number; bx: number; by: number; r: number; tone: number; taper?: number; w?: number };
type MembraneScene = {
  cells: readonly MembraneCell[];
  strands: readonly MembraneStrand[];
  blend?: number;
  wobble?: number;
  contour?: number;
  time?: number;
};
type Rgb = [number, number, number];
type MembranePalette = { tones: Rgb[]; deep: Rgb[]; paper: Rgb; ink: Rgb; dim: number; glow: number; css: { tones: string[]; deep: string[] } };
const MEMBRANE_LIMITS = { cells: 18, strands: 8 } as const;

const rgb = (hex: string): Rgb => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255) as Rgb;
function palette(tones: string[], deep: string[], dim: number, glow: number): MembranePalette {
  return { tones: tones.map(rgb), deep: deep.map(rgb), paper: rgb("#FAF8F3"), ink: rgb("#0F1B2D"), dim, glow, css: { tones, deep } };
}
// Tone 0 the lead and the left of the body, 1 the passages, 2 the partner and the right, 3 the check.
// Light: pale teal and soft grey-blue on paper. Dark: the same teal glowing on navy, the bodies dimmed.
const PALETTES: Record<Mode, MembranePalette> = {
  light: palette(["#A6E6DA", "#BBD6E2", "#C6D4E5", "#E9E2CB"], ["#6CCDBD", "#8DB6C9", "#99AFC9", "#D2C6A1"], 0, 0.16),
  dark: palette(["#2DD4BF", "#4D8A9C", "#5A7A9B", "#B7A67C"], ["#1EA593", "#3A6E80", "#45617F", "#958559"], 0.42, 0.5),
};

const vertexSource = `
attribute vec2 aPosition;
void main() { gl_Position = vec4(aPosition, 0.0, 1.0); }
`;
const fragmentSource = `
precision highp float;
uniform vec2 uSize;
uniform float uDpr;
uniform float uTime;
uniform int uCellCount;
uniform vec4 uCellA[${MEMBRANE_LIMITS.cells}];
uniform vec4 uCellB[${MEMBRANE_LIMITS.cells}];
uniform int uStrandCount;
uniform vec4 uStrandA[${MEMBRANE_LIMITS.strands}];
uniform vec4 uStrandB[${MEMBRANE_LIMITS.strands}];
uniform vec3 uTone[4];
uniform vec3 uDeep[4];
uniform vec3 uPaper; uniform vec3 uInk; uniform float uDim; uniform float uGlow;
uniform float uBlend;
uniform float uWobble;
uniform float uContour;

vec3 toneAt(int t) { if (t <= 0) return uTone[0]; if (t == 1) return uTone[1]; if (t == 2) return uTone[2]; return uTone[3]; }
vec3 deepAt(int t) { if (t <= 0) return uDeep[0]; if (t == 1) return uDeep[1]; if (t == 2) return uDeep[2]; return uDeep[3]; }
vec3 toneMix(float t) { t = clamp(t, 0.0, 3.0); int a = int(floor(t)); return mix(toneAt(a), toneAt(a + 1), fract(t)); }
vec3 deepMix(float t) { t = clamp(t, 0.0, 3.0); int a = int(floor(t)); return mix(deepAt(a), deepAt(a + 1), fract(t)); }

float sdCell(vec2 p, vec4 a, vec4 b) {
  vec2 q = p - a.xy;
  float c = cos(b.w), s = sin(b.w);
  q = vec2(c * q.x + s * q.y, -s * q.x + c * q.y);
  float r = min(b.x, min(a.z, a.w));
  vec2 e = max(a.zw - vec2(r), 0.0);
  vec2 d = abs(q) - e;
  return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - r;
}
float sdStrand(vec2 p, vec4 a, vec4 b) {
  vec2 pa = p - a.xy, ba = a.zw - a.xy;
  float h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-4), 0.0, 1.0);
  return length(pa - ba * h) - b.x * (1.0 - b.w * h);
}
float smin(float a, float b, float k) {
  float h = max(k - abs(a - b), 0.0) / k;
  return min(a, b) - h * h * k * 0.25;
}

void main() {
  vec2 p = vec2(gl_FragCoord.x, uSize.y * uDpr - gl_FragCoord.y) / uDpr;
  float k = max(uBlend, 1.0);
  float d = 1e5, wsum = 0.0;
  vec3 tone = vec3(0.0), deep = vec3(0.0);
  for (int i = 0; i < ${MEMBRANE_LIMITS.cells}; i++) {
    if (i >= uCellCount) break;
    vec4 a = uCellA[i], b = uCellB[i];
    if (a.z <= 0.05 || a.w <= 0.05) continue;
    float di = sdCell(p, a, b);
    d = smin(d, di, k);
    float w = exp(-clamp(di, -80.0, 200.0) / (k * 1.5)) * b.z;
    tone += w * toneMix(b.y); deep += w * deepMix(b.y); wsum += w;
  }
  for (int i = 0; i < ${MEMBRANE_LIMITS.strands}; i++) {
    if (i >= uStrandCount) break;
    vec4 a = uStrandA[i], b = uStrandB[i];
    if (b.x <= 0.05) continue;
    float di = sdStrand(p, a, b);
    d = smin(d, di, k);
    float w = exp(-clamp(di, -80.0, 200.0) / (k * 1.5)) * b.z;
    tone += w * toneMix(b.y); deep += w * deepMix(b.y); wsum += w;
  }
  tone /= max(wsum, 1e-5); deep /= max(wsum, 1e-5);
  d += (sin(p.x * 0.021 + uTime * 0.9) * sin(p.y * 0.027 - uTime * 0.7) * 0.6 + sin((p.x - p.y) * 0.017 + uTime * 1.3) * 0.4) * uWobble;
  float cover = 1.0 - smoothstep(-0.9, 0.9, d);
  float halo = exp(-max(d, 0.0) / 34.0) * (1.0 - cover) * uGlow;
  if (cover <= 0.003 && halo <= 0.004) discard;
  float depth = clamp(-d / 56.0, 0.0, 1.0);
  vec3 body = mix(mix(tone, uPaper, 0.12), deep, depth * 0.26);
  float rim = 1.0 - smoothstep(0.0, 1.9, abs(d + 1.1));
  body = mix(body, deep, rim * 0.6);
  float ring = abs(fract(-d / 14.0) - 0.5);
  float lines = (1.0 - smoothstep(0.06, 0.16, ring)) * smoothstep(0.0, -7.0, d) * exp(d / 90.0) * uContour;
  body = mix(body, deep, lines * 0.34);
  body = mix(body, uInk, uDim);
  vec3 light = mix(tone, vec3(1.0), 0.25);
  gl_FragColor = vec4(body * cover + light * halo, cover + halo);
}
`;
const UNIFORMS = ["uSize", "uDpr", "uTime", "uCellCount", "uCellA", "uCellB", "uStrandCount", "uStrandA", "uStrandB", "uTone", "uDeep", "uPaper", "uInk", "uDim", "uGlow", "uBlend", "uWobble", "uContour"];

type Program = { gl: WebGLRenderingContext; program: WebGLProgram; buffer: WebGLBuffer; shaders: WebGLShader[]; at: Record<string, WebGLUniformLocation | null> };
type Renderer = { status: "webgl" | "fallback"; resize(w: number, h: number, dpr: number): void; setPalette(p: MembranePalette): void; draw(s: MembraneScene): void; dispose(): void };

function createRenderer(canvas: HTMLCanvasElement): Renderer {
  let width = 1, height = 1, dpr = 1, disposed = false;
  let colors = PALETTES.light;
  const cellA = new Float32Array(MEMBRANE_LIMITS.cells * 4), cellB = new Float32Array(MEMBRANE_LIMITS.cells * 4);
  const strandA = new Float32Array(MEMBRANE_LIMITS.strands * 4), strandB = new Float32Array(MEMBRANE_LIMITS.strands * 4);

  function compile(gl: WebGLRenderingContext, type: number, source: string, shaders: WebGLShader[]) {
    const shader = gl.createShader(type);
    if (!shader) throw new Error("Shader allocation failed");
    shaders.push(shader);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader) ?? "Shader compilation failed");
    return shader;
  }

  function setup(): Program | null {
    let gl: WebGLRenderingContext | null = null;
    try {
      gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: true, antialias: false, depth: false, stencil: false, powerPreference: "low-power" });
    } catch {
      gl = null;
    }
    if (!gl) return null;
    const shaders: WebGLShader[] = [];
    try {
      const program = gl.createProgram();
      if (!program) throw new Error("Program allocation failed");
      gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, vertexSource, shaders));
      gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragmentSource, shaders));
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) ?? "Program link failed");
      const buffer = gl.createBuffer();
      if (!buffer) throw new Error("Buffer allocation failed");
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      gl.useProgram(program);
      const position = gl.getAttribLocation(program, "aPosition");
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
      const at: Record<string, WebGLUniformLocation | null> = {};
      for (const name of UNIFORMS) at[name] = gl.getUniformLocation(program, name);
      gl.disable(gl.DEPTH_TEST);
      gl.disable(gl.BLEND);
      gl.clearColor(0, 0, 0, 0);
      return { gl, program, buffer, shaders, at };
    } catch (error) {
      console.warn("Membrane: WebGL unavailable, painting a flat fallback.", error);
      for (const shader of shaders) gl.deleteShader(shader);
      return null;
    }
  }

  let program = setup();
  let flat = program ? null : canvas.getContext("2d");

  function drawFlat(scene: MembraneScene) {
    const ctx = flat;
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.lineCap = "round";
    const tone = (t: number) => Math.round(Math.min(3, Math.max(0, t)));
    for (const s of scene.strands) {
      if (s.r <= 0.05) continue;
      ctx.strokeStyle = colors.css.tones[tone(s.tone)];
      ctx.lineWidth = s.r * 2 * (1 - (s.taper ?? 0) * 0.5);
      ctx.beginPath();
      ctx.moveTo(s.ax, s.ay);
      ctx.lineTo(s.bx, s.by);
      ctx.stroke();
    }
    for (const c of scene.cells) {
      if (c.hw <= 0.05 || c.hh <= 0.05) continue;
      ctx.save();
      ctx.translate(c.x, c.y);
      ctx.rotate(c.rot ?? 0);
      ctx.fillStyle = colors.css.tones[tone(c.tone)];
      ctx.beginPath();
      ctx.roundRect(-c.hw, -c.hh, c.hw * 2, c.hh * 2, Math.min(c.r, c.hw, c.hh));
      ctx.fill();
      ctx.restore();
    }
  }

  function drawGl(scene: MembraneScene) {
    const { gl, at } = program!;
    if (gl.isContextLost()) return;
    const cells = scene.cells.slice(0, MEMBRANE_LIMITS.cells), strands = scene.strands.slice(0, MEMBRANE_LIMITS.strands);
    cellA.fill(0); cellB.fill(0); strandA.fill(0); strandB.fill(0);
    cells.forEach((c, i) => { cellA.set([c.x, c.y, c.hw, c.hh], i * 4); cellB.set([c.r, c.tone, c.w ?? 1, c.rot ?? 0], i * 4); });
    strands.forEach((s, i) => { strandA.set([s.ax, s.ay, s.bx, s.by], i * 4); strandB.set([s.r, s.tone, s.w ?? 1, s.taper ?? 0], i * 4); });
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.uniform2f(at.uSize, width, height);
    gl.uniform1f(at.uDpr, dpr);
    gl.uniform1f(at.uTime, scene.time ?? 0);
    gl.uniform1i(at.uCellCount, cells.length);
    gl.uniform4fv(at.uCellA, cellA);
    gl.uniform4fv(at.uCellB, cellB);
    gl.uniform1i(at.uStrandCount, strands.length);
    gl.uniform4fv(at.uStrandA, strandA);
    gl.uniform4fv(at.uStrandB, strandB);
    gl.uniform3fv(at.uTone, colors.tones.flat());
    gl.uniform3fv(at.uDeep, colors.deep.flat());
    gl.uniform3f(at.uPaper, ...colors.paper);
    gl.uniform3f(at.uInk, ...colors.ink);
    gl.uniform1f(at.uDim, colors.dim);
    gl.uniform1f(at.uGlow, colors.glow);
    gl.uniform1f(at.uBlend, scene.blend ?? 26);
    gl.uniform1f(at.uWobble, scene.wobble ?? 0);
    gl.uniform1f(at.uContour, scene.contour ?? 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  return {
    get status() {
      return program ? ("webgl" as const) : ("fallback" as const);
    },
    resize(nextWidth, nextHeight, nextDpr) {
      width = Math.max(1, nextWidth);
      height = Math.max(1, nextHeight);
      // At most about 1.4 megapixels, whatever the screen: the field is soft, so it never shows.
      dpr = Math.max(0.5, Math.min(Math.max(nextDpr, 1), 2, Math.sqrt(1_400_000 / (width * height))));
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
    },
    setPalette(next) {
      colors = next;
    },
    draw(scene) {
      if (disposed) return;
      if (program) drawGl(scene);
      else drawFlat(scene);
    },
    dispose() {
      disposed = true;
      if (program) {
        const { gl, buffer, program: p, shaders } = program;
        if (!gl.isContextLost()) {
          gl.deleteBuffer(buffer);
          gl.deleteProgram(p);
          for (const shader of shaders) gl.deleteShader(shader);
        }
        program = null;
      }
      flat = null;
    },
  };
}

type MembraneHandle = { draw(scene: MembraneScene): void };

/** The membrane's canvas over the whole hero: it owns measuring, pixel bounds, colours and context loss. */
function Membrane({ ref, mode, onMeasure }: { ref: React.Ref<MembraneHandle>; mode: Mode; onMeasure: () => void }) {
  const host = React.useRef<HTMLDivElement>(null), canvas = React.useRef<HTMLCanvasElement>(null);
  const renderer = React.useRef<Renderer | null>(null), last = React.useRef<MembraneScene | null>(null);
  const measure = React.useRef(onMeasure);
  React.useLayoutEffect(() => {
    measure.current = onMeasure;
  }, [onMeasure]);
  React.useImperativeHandle(ref, () => ({
    draw(scene) {
      last.current = scene;
      renderer.current?.draw(scene);
    },
  }), []);
  React.useEffect(() => {
    renderer.current?.setPalette(PALETTES[mode]);
    if (last.current) renderer.current?.draw(last.current);
  }, [mode]);
  React.useEffect(() => {
    const element = host.current, surface = canvas.current;
    if (!element || !surface) return;
    let current = createRenderer(surface);
    let measured = "";
    renderer.current = current;
    current.setPalette(PALETTES[mode]);
    const resize = () => {
      const width = Math.max(1, element.clientWidth), height = Math.max(1, element.clientHeight), dpr = window.devicePixelRatio || 1;
      const key = `${width}x${height}@${dpr}`;
      if (key === measured) return;
      measured = key;
      current.resize(width, height, dpr);
      element.dataset.renderer = current.status;
      measure.current();
      if (last.current) current.draw(last.current);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(element);
    const lost = (event: Event) => {
      event.preventDefault();
      element.dataset.renderer = "lost";
    };
    const restored = () => {
      current.dispose();
      current = createRenderer(surface);
      renderer.current = current;
      current.setPalette(PALETTES[mode]);
      measured = "";
      resize();
    };
    surface.addEventListener("webglcontextlost", lost);
    surface.addEventListener("webglcontextrestored", restored);
    resize();
    return () => {
      observer.disconnect();
      surface.removeEventListener("webglcontextlost", lost);
      surface.removeEventListener("webglcontextrestored", restored);
      current.dispose();
      renderer.current = null;
    };
    // The palette follows `mode` in its own effect; the renderer is made once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div ref={host} className="pb-membrane">
      <canvas ref={canvas} />
    </div>
  );
}

/* ── The story: one question, its two passages, the answer and its check ── */

const SLOTS = 12;
const PASSAGES = story.passages.length;
const ROWS = PASSAGES + 4; // the question, the reading, each passage, the answer, the check
const REPLY = 2 + PASSAGES;
const CHECK = REPLY + 1;
const LAST = 5;
const START_MS = 900; // the page starts typing the question this long after the hero is ready
const words = ["One", "Two", "Three", "Four"];

export const beats = [
  { cue: "A question about a filing.", label: "Ready" },
  { cue: "FilingLens reads it: the company, the years, the kind of question.", label: "Read" },
  { cue: `Read as ${story.reading.join(" · ")}.`, label: "Ask" },
  { cue: `${words[PASSAGES - 1] ?? PASSAGES} passages from ${story.filing} hold the answer.`, label: "Find" },
  { cue: "Each sentence cites its passage, and a check matches every quote and amount.", label: "Answer" },
  { cue: "An answer you can check.", label: "Done" },
] as const;

type Kind = "passage" | "filing";
type Thing = { kind: Kind; title: string; sub: string; icon: string };
const KIND_TITLE: Record<Kind, string> = { passage: "Passage", filing: "Filing" };

/** What floats round the panel: the cited passages first, one on each side, then the snapshot's other filings. */
const ENV: (Thing | null)[] = (() => {
  const passages = story.passages.map((p): Thing => ({ kind: "passage", title: `Item ${p.item}`, sub: story.filing, icon: "file-text" }));
  const filings = story.others.slice(0, SLOTS - PASSAGES - 1).map((filing): Thing => {
    const [ticker, form, year] = filing.split(" ");
    return { kind: "filing", title: `${ticker} ${form}`, sub: year, icon: "file" };
  });
  return [...passages, ...filings, ...Array<null>(SLOTS - passages.length - filings.length).fill(null)];
})();

/* ── World: plain objects the timelines tween and the frame loop paints. Positions are px/py on purpose:
 * Motion treats keys called x and y as transforms. ── */

type Cell = { px: number; py: number; hw: number; hh: number; r: number; tone: number; rot: number; w: number };
type Strand = { ax: number; ay: number; bx: number; by: number; r: number; tone: number; taper: number; w: number };
/** A floating thing: `s` its scale, `t` its label, `free` its drift (1 floating, 0 held), `rip` its ring, `flash` its light. */
type Node = { px: number; py: number; o: number; s: number; t: number; free: number; rip: number; flash: number };
/** A row: `g` its glyph coming into being, `p` the ring that ripples off it. */
type Row = { o: number; dy: number; p: number; g: number };
type Eye = { o: number; lid: number };
type World = {
  env: { free: number; breath: number; wobble: number; underline: number; pulse: number; contour: number; panel: number };
  A: Cell; B: Cell; O: Cell[]; PL: Cell; PR: Cell; K: Cell[]; U: Cell[];
  strands: Strand[]; nodes: Node[]; rows: Row[]; eyes: Eye[];
  gaze: { px: number; py: number; w: number };
  lines: { a: number; check: number; typing: number };
  capsule: { o: number };
};
const ORGANISMS = 6, RADII = [26, 23, 13, 11, 15, 10];
const cell = (tone: number, w = 1): Cell => ({ px: 0, py: 0, hw: 0, hh: 0, r: 0, tone, rot: 0, w });
const strand = (tone: number): Strand => ({ ax: 0, ay: 0, bx: 0, by: 0, r: 0, tone, taper: 0, w: 1 });
function createWorld(): World {
  return {
    env: { free: 1, breath: 0, wobble: 1.2, underline: 1, pulse: 0, contour: 0, panel: 0 },
    A: cell(0), B: cell(2), O: [cell(0), cell(2), cell(0), cell(2)], PL: cell(0), PR: cell(2),
    K: [cell(1, 1.4), cell(1, 1.4), cell(3, 1.4), cell(1, 1.2)],
    U: Array.from({ length: Math.max(2, PASSAGES) }, () => cell(1)),
    strands: Array.from({ length: 8 }, (_, i) => strand(i > 5 ? 0 : 1)),
    nodes: Array.from({ length: SLOTS }, () => ({ px: 0, py: 0, o: 0, s: 1, t: 1, free: 1, rip: 1, flash: 0 })),
    rows: Array.from({ length: ROWS }, () => ({ o: 0, dy: 0, p: 0, g: 0 })),
    eyes: Array.from({ length: ORGANISMS }, () => ({ o: 1, lid: 0 })),
    gaze: { px: 0, py: 0, w: 0 },
    lines: { a: 0, check: 0, typing: 0 },
    capsule: { o: 1 },
  };
}

/* ── Roaming: six organisms steer across the hero while free ── */

type Point = { x: number; y: number };
type Roam = { x: number; y: number; vx: number; vy: number; tx: number; ty: number; wait: number; r: number; seed: number };
type Capture = { t0: number; from: Point[] };
const createRoam = (): Roam[] => RADII.map((r, i) => ({ x: 0, y: 0, vx: 0, vy: 0, tx: 0, ty: 0, wait: 0, r, seed: i * 1.7 }));
/** Critically damped approach that keeps whatever velocity the body already has. */
function damp(r: Roam, tx: number, ty: number, smooth: number, dt: number) {
  const omega = 2 / smooth, x = omega * dt, ex = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const cx = r.x - tx, cy = r.y - ty, ux = (r.vx + omega * cx) * dt, uy = (r.vy + omega * cy) * dt;
  r.vx = (r.vx - omega * ux) * ex; r.vy = (r.vy - omega * uy) * ex; r.x = tx + (cx + ux) * ex; r.y = ty + (cy + uy) * ex;
}

/* ── Layout: everything measured from the real capsule, panel and rows, against the hero ── */

type Size = { w: number; h: number };
type Rect = { cx: number; cy: number; hw: number; hh: number };
type Layout = {
  W: number; H: number; k: number; field: Rect; panel: Rect & { left: number; right: number; top: number; bottom: number };
  endL: Point; endR: Point; docks: Point[]; rest: Point[]; bounds: { x0: number; y0: number; x1: number; y1: number };
  slots: Point[]; rims: Point[]; roomy: boolean; rows: Point[]; reply: { x: number; y: number; w: number; h: number };
};
/** An element's offset inside `panel`, its positioned ancestor, unmoved by the transforms the frame loop sets. */
function offsetIn(el: HTMLElement, panel: HTMLElement) {
  let x = 0, y = 0;
  for (let node: HTMLElement | null = el; node && node !== panel; node = node.offsetParent as HTMLElement | null) {
    x += node.offsetLeft;
    y += node.offsetTop;
  }
  return { x, y };
}
function measure(stage: HTMLElement, capsule: HTMLElement, panel: HTMLElement, rowEls: (HTMLElement | null)[], replyEl: HTMLElement | null, heads: Element[]): Layout | null {
  const s = stage.getBoundingClientRect(), f = capsule.getBoundingClientRect(), p = panel.getBoundingClientRect();
  if (!s.width || !f.width || !p.width) return null;
  const W = s.width, H = s.height, cx = f.left - s.left + f.width / 2, cy = f.top - s.top + f.height / 2;
  const hw = f.width / 2 + 10, hh = f.height / 2 + 6, k = Math.min(1.8, Math.max(0.62, hw / 290));
  const pl = p.left - s.left, pt = p.top - s.top, pcx = pl + p.width / 2, pcy = pt + p.height / 2, phw = p.width / 2 + 10, phh = p.height / 2 + 8;
  const inset = Math.min(90, H * 0.1), bounds = { x0: 40 * k, y0: inset, x1: W - 40 * k, y1: H - inset };
  const place = (x: number, y: number): Point => ({ x: Math.min(bounds.x1, Math.max(bounds.x0, x)), y: Math.min(bounds.y1, Math.max(bounds.y0, y)) });
  const endL = { x: cx - hw + hh * 0.3, y: cy }, endR = { x: cx + hw - hh * 0.3, y: cy };
  const rows = Array.from({ length: ROWS }, (_, i) => {
    const el = rowEls[i];
    if (!el) return { x: pcx, y: pcy };
    const o = offsetIn(el, panel);
    return { x: pl + o.x + 10, y: pt + o.y + el.offsetHeight / 2 };
  });
  const r = replyEl ? offsetIn(replyEl, panel) : null;
  const reply = replyEl && r ? { x: pl + r.x, y: pt + r.y, w: replyEl.offsetWidth, h: replyEl.offsetHeight } : { x: pcx - 60, y: pcy, w: 120, h: 40 };
  const left = pcx - phw, right = pcx + phw, top = pcy - phh, bottom = pcy + phh;
  // Things carry a label when there is room beside the panel; otherwise only their blob.
  const roomy = left >= 230 * k && W - right >= 230 * k;
  const rects = heads.map((el) => el.getBoundingClientRect()).filter((rect) => rect.width);
  const head = rects.length
    ? { l: Math.min(...rects.map((h) => h.left)) - s.left, r: Math.max(...rects.map((h) => h.right)) - s.left, t: Math.min(...rects.map((h) => h.top)) - s.top, b: Math.max(...rects.map((h) => h.bottom)) - s.top }
    : null;
  const slots = scatter(W, H, k, { left, right }, roomy, head);
  const cl = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  // A tendril leaves the panel from the edge nearest the thing.
  const rims = slots.map((sl) =>
    sl.x < left || sl.x > right
      ? { x: sl.x < left ? left + 6 : right - 6, y: cl(sl.y, top + 24 * k, bottom - 24 * k) }
      : { x: cl(sl.x, left + 24 * k, right - 24 * k), y: sl.y < pcy ? top + 6 : bottom - 6 },
  );
  return {
    W, H, k, field: { cx, cy, hw, hh }, panel: { cx: pcx, cy: pcy, hw: phw, hh: phh, left, right, top, bottom },
    endL, endR, bounds,
    docks: [endL, endR, { x: cx - hw * 0.35, y: cy - hh + 3 }, { x: cx + hw * 0.3, y: cy - hh + 3 }, { x: cx - hw * 0.05, y: cy + hh - 3 }, { x: cx + hw * 0.5, y: cy + hh - 3 }],
    rest: [place(cx - hw * 0.75, cy - hh - 80 * k), place(cx + hw * 0.7, cy + hh + 78 * k), place(cx - hw - 150 * k, cy - 40 * k), place(cx + hw * 0.25, cy - hh - 150 * k), place(cx - hw * 0.3, cy + hh + 140 * k), place(cx + hw + 160 * k, cy + 30 * k)],
    slots, rims, roomy, rows, reply,
  };
}
/** How far a labelled thing's centre stays from the headline's end: half its body, its drift, and air. */
const clearX = (k: number) => 50 * k + 6;
/** The float slots over both sides of the panel: each side cut into rows, one thing a row, shuffled by a seeded
 * sampler, so the layout reads scattered yet is the same on every visit and no two things stack. */
function scatter(W: number, H: number, k: number, panel: { left: number; right: number }, roomy: boolean, head: { l: number; r: number; t: number; b: number } | null): Point[] {
  let seed = 11;
  const rnd = () => {
    seed = (seed * 48271) % 2147483647;
    return seed / 2147483647;
  };
  const labelW = roomy ? 150 * k : 0, rowH = roomy ? 62 * k : 44, per = SLOTS / 2;
  const bands = roomy
    ? [{ x0: 34 * k + labelW, x1: panel.left - 74 * k }, { x0: panel.right + 74 * k, x1: W - 34 * k - labelW }]
    : [{ x0: 24, x1: Math.max(24, panel.left - 44) }, { x0: Math.min(W - 24, panel.right + 44), x1: W - 24 }];
  const y0 = roomy ? 108 * k : 92, y1 = H - (roomy ? 134 * k : 124);
  const rows = Math.max(per, Math.floor((y1 - y0) / rowH)), step = (y1 - y0) / rows, slack = Math.max(0, step - rowH);
  const pick = () => {
    const idx = Array.from({ length: rows }, (_, i) => i);
    for (let i = idx.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1));
      [idx[i], idx[j]] = [idx[j], idx[i]];
    }
    return idx.slice(0, per);
  };
  const chosen = [pick(), pick()], pts: Point[] = [];
  const edge = roomy ? 30 * k : 22;
  for (let i = 0; i < SLOTS; i++) {
    const b = bands[i % 2], row = chosen[i % 2][i >> 1];
    pts.push({ x: Math.min(W - edge, Math.max(edge, b.x0 + rnd() * (b.x1 - b.x0))), y: y0 + row * step + rowH / 2 + rnd() * slack });
  }
  // A thing whose row crosses the headline moves out past its end, or that whole side starts below it.
  if (head) {
    const hx = roomy ? clearX(k) : 31, hy = (roomy ? 28 * k : 18) + 6 * k + 4;
    const hits = (p: Point) => p.y + hy > head.t && p.y - hy < head.b && p.x + hx > head.l && p.x - hx < head.r;
    for (const side of [0, 1]) {
      const b = bands[side], out = side ? head.r + hx : head.l - hx, room = side ? out <= Math.max(b.x0, b.x1) : out >= Math.min(b.x0, b.x1);
      const mine = pts.filter((_, i) => i % 2 === side);
      if (!room && mine.some(hits)) {
        const lo = y0 + rowH / 2, hi = y1 - rowH / 2, top = Math.min(hi, head.b + hy);
        if (hi > lo) mine.forEach((p) => { p.y = top + ((p.y - lo) * (hi - top)) / (hi - lo); });
      }
      mine.forEach((p) => { if (hits(p)) p.x = out; });
    }
  }
  return pts;
}
const at = (p: Point) => ({ px: p.x, py: p.y });
const zero = { hw: 0, hh: 0, r: 0 };
/** A pocket of membrane grown round a shape. */
const pocket = (size: Size, k: number, anchor: Point) => ({ px: anchor.x, py: anchor.y, hw: size.w / 2 + 9 * k, hh: size.h / 2 + 9 * k, r: Math.min(size.h / 2 + 9 * k, 22 * k) });

/* ── Poses: the still of each beat, so a seek, a resize or a stop always lands somewhere true ── */

function floatPose(w: World, L: Layout) {
  w.nodes.forEach((n, i) => Object.assign(n, { ...at(L.slots[i]), o: ENV[i] ? 1 : 0, s: 1, t: 1, free: 1, rip: 1, flash: 0 }));
}
function restPose(w: World, L: Layout, roam: Roam[]) {
  const k = L.k;
  Object.assign(w.env, { free: 1, breath: 0, wobble: 1.2, underline: 1, pulse: 0, contour: 0, panel: 0 });
  [w.A, w.B, ...w.O].forEach((c, i) => {
    const r = RADII[i] * k;
    Object.assign(c, { ...at(L.rest[i]), hw: r, hh: r, r, rot: 0 });
    Object.assign(roam[i], { x: L.rest[i].x, y: L.rest[i].y, vx: 0, vy: 0, r, wait: 0, tx: L.rest[i].x, ty: L.rest[i].y });
  });
  for (const c of [w.PL, w.PR, ...w.K, ...w.U]) Object.assign(c, { px: L.field.cx, py: L.field.cy, ...zero, rot: 0 });
  for (const s of w.strands) Object.assign(s, { ax: L.field.cx, ay: L.field.cy, bx: L.field.cx, by: L.field.cy, r: 0, taper: 0 });
  floatPose(w, L);
  for (const r of w.rows) Object.assign(r, { o: 0, dy: 0, p: 0, g: 0 });
  for (const e of w.eyes) Object.assign(e, { o: 1, lid: 0 });
  Object.assign(w.gaze, { px: L.field.cx, py: L.field.cy, w: 0 });
  Object.assign(w.lines, { a: 0, check: 0, typing: 0 });
  w.capsule.o = 1;
}
/** The settled bonded line: two heads at the capsule's ends, membrane between. */
function bondedPose(w: World, L: Layout, roam: Roam[]) {
  restPose(w, L, roam);
  const e = L.field.hh + 3, F = L.field;
  Object.assign(w.env, { free: 0, breath: 1, wobble: 1.5, underline: 0, contour: 0.7 });
  Object.assign(w.A, { ...at(L.endL), hw: e, hh: e, r: e });
  Object.assign(w.B, { ...at(L.endR), hw: e, hh: e, r: e });
  [w.A, w.B, ...w.O].forEach((c, i) => {
    Object.assign(roam[i], { x: L.docks[i].x, y: L.docks[i].y, vx: 0, vy: 0 });
    if (i > 1) Object.assign(c, { ...at(L.docks[i]), ...zero });
  });
  const half = (F.cx - L.endL.x) / 2 + 8;
  Object.assign(w.PL, { px: L.endL.x + half, py: F.cy, hw: half, hh: F.hh + 2, r: F.hh + 2 });
  Object.assign(w.PR, { px: L.endR.x - half, py: F.cy, hw: half, hh: F.hh + 2, r: F.hh + 2 });
  w.eyes.forEach((e, i) => { if (i > 0) Object.assign(e, { o: 0, lid: 1 }); });
  Object.assign(w.gaze, { px: F.cx, py: F.cy, w: 1 });
}
const headL = (L: Layout) => ({ px: L.panel.left + 30 * L.k, py: L.panel.top + 4 * L.k, hw: 22 * L.k, hh: 22 * L.k, r: 22 * L.k });
const headR = (L: Layout) => ({ px: L.panel.right - 30 * L.k, py: L.panel.top + 4 * L.k, hw: 20 * L.k, hh: 20 * L.k, r: 20 * L.k });
const bodyL = (L: Layout) => ({ px: L.panel.cx - L.panel.hw * 0.22, py: L.panel.cy, hw: L.panel.hw * 0.78, hh: L.panel.hh, r: 30 * L.k });
const bodyR = (L: Layout) => ({ px: L.panel.cx + L.panel.hw * 0.22, py: L.panel.cy, hw: L.panel.hw * 0.78, hh: L.panel.hh, r: 30 * L.k });
/** The open panel with what every beat before `upTo` revealed. */
function panelPose(w: World, L: Layout, roam: Roam[], upTo: number) {
  bondedPose(w, L, roam);
  Object.assign(w.env, { panel: 1, contour: 0.3 });
  w.capsule.o = 0;
  Object.assign(w.A, headL(L));
  Object.assign(w.B, headR(L));
  Object.assign(w.PL, bodyL(L));
  Object.assign(w.PR, bodyR(L));
  Object.assign(w.gaze, { px: L.panel.cx, py: L.panel.top + 40 * L.k, w: 1 });
  w.rows[0].o = 1;
  const done = (i: number) => Object.assign(w.rows[i], { o: 1, g: 1 });
  if (upTo > 2) done(1);
  if (upTo > 3) for (let i = 0; i < PASSAGES; i++) done(2 + i);
  if (upTo > 4) {
    w.rows[REPLY].o = 1;
    Object.assign(w.lines, { a: 1, check: 1 });
    done(CHECK);
  }
}

/* ── Choreography: one Motion sequence per beat ── */

type Beat = { seq: AnimationSequence; still: number };
const flow = [0.6, 0, 0.15, 1] as const, settle = [0.4, 0, 0.2, 1] as const, inOut = "easeInOut" as const, out = "easeOut" as const;
const spring = (stiffness: number, damping: number) => ({ type: "spring" as const, stiffness, damping });
const lookAt = (w: World, p: Point, t: number, d = 0.4): AnimationSequence[number] => [w.gaze, { ...at(p), w: 1 }, { duration: d, at: t }];
const home = (w: World, L: Layout, t: number): AnimationSequence[number] => [w.gaze, { px: L.panel.cx, py: L.panel.top + 40 * L.k }, { duration: 0.5, at: t }];
/** A row settles into place, quietly. */
const land = (w: World, L: Layout, i: number, t: number): AnimationSequence => [
  [w.rows[i], { dy: 8 * L.k, g: 0, p: 0 }, { duration: 0.01, at: 0 }],
  [w.rows[i], { o: 1, dy: 0 }, { duration: 0.5, ease: settle, at: t }],
];
/** The row's glyph pops into being and a ring ripples off it: what was reached has arrived. */
const ripple = (w: World, i: number, t: number): AnimationSequence => [
  [w.rows[i], { p: 1 }, { duration: 0.08, at: t }],
  [w.rows[i], { p: 0 }, { duration: 0.85, ease: out, at: t + 0.1 }],
];
const arrive = (w: World, i: number, t: number): AnimationSequence => [[w.rows[i], { g: 1 }, { ...spring(240, 14), at: t }], ...ripple(w, i, t + 0.02)];
const widen = (w: World, t: number, d = 0.7): AnimationSequence => [[w.eyes[0], { lid: -0.2 }, { duration: 0.2, at: t }], [w.eyes[0], { lid: 0 }, { duration: 0.35, at: t + d }]];
const blink = (w: World, t: number): AnimationSequence => [[w.eyes[0], { lid: 1 }, { duration: 0.1, at: t }], [w.eyes[0], { lid: 0 }, { duration: 0.22, at: t + 0.12 }]];

/** Beat 1: the organisms fly in (the roam step); the timeline handles contact and the spread. */
function bond(w: World, L: Layout): Beat {
  const e = L.field.hh + 3, F = L.field, half = (F.cx - L.endL.x) / 2 + 8;
  return {
    still: 3,
    seq: [
      [w.env, { underline: 3.2 }, { duration: 0.9, ease: out, at: 0 }],
      lookAt(w, { x: F.cx, y: F.cy }, 0.1, 0.3),
      [w.env, { free: 0 }, { duration: 0.25, at: 0.95 }],
      [w.A, { hw: e, hh: e, r: e }, { ...spring(300, 14), at: 0.95 }],
      [w.B, { hw: e, hh: e, r: e }, { ...spring(300, 14), at: 1.0 }],
      ...w.O.map((c, i): AnimationSequence[number] => [c, zero, { duration: 0.4, at: 1.3 + i * 0.08 }]),
      ...w.eyes.slice(2).map((eye, i): AnimationSequence[number] => [eye, { o: 0 }, { duration: 0.25, at: 1.2 + i * 0.08 }]),
      [w.PL, { px: L.endL.x + 2, py: F.cy, hw: 2, hh: F.hh + 2, r: F.hh + 2 }, { duration: 0.01, at: 0.98 }],
      [w.PR, { px: L.endR.x - 2, py: F.cy, hw: 2, hh: F.hh + 2, r: F.hh + 2 }, { duration: 0.01, at: 1.04 }],
      [w.PL, { px: L.endL.x + half, hw: half }, { duration: 1.05, ease: flow, at: 1.0 }],
      [w.PR, { px: L.endR.x - half, hw: half }, { duration: 1.05, ease: flow, at: 1.06 }],
      [w.env, { underline: 0 }, { duration: 0.9, at: 1.0 }],
      [w.eyes[1], { lid: 1 }, { duration: 0.35, at: 1.2 }],
      [w.eyes[1], { o: 0 }, { duration: 0.4, at: 1.55 }],
      [w.PL, { hh: F.hh + 9 }, { duration: 0.16, ease: out, at: 2.0 }],
      [w.PR, { hh: F.hh + 9 }, { duration: 0.16, ease: out, at: 2.04 }],
      [w.A, { hw: e + 5, hh: e + 5, r: e + 5 }, { duration: 0.16, ease: out, at: 2.0 }],
      [w.B, { hw: e + 5, hh: e + 5, r: e + 5 }, { duration: 0.16, ease: out, at: 2.04 }],
      [w.PL, { hh: F.hh + 2 }, { ...spring(170, 13), at: 2.18 }],
      [w.PR, { hh: F.hh + 2 }, { ...spring(170, 13), at: 2.22 }],
      [w.A, { hw: e, hh: e, r: e }, { ...spring(170, 13), at: 2.18 }],
      [w.B, { hw: e, hh: e, r: e }, { ...spring(170, 13), at: 2.22 }],
      [w.eyes[0], { lid: 0.5 }, { duration: 0.12, at: 2.05 }],
      [w.eyes[0], { lid: 0 }, { duration: 0.3, at: 2.3 }],
      [w.env, { contour: 0.7 }, { duration: 1, at: 1.6 }],
      [w.env, { wobble: 1.5 }, { duration: 0.8, at: 2.0 }],
      [w.env, { breath: 1 }, { duration: 0.6, at: 2.4 }],
    ],
  };
}
/** Beat 2: the line grows into the panel, the question lifts into it, and how it was read lands below. */
function launch(w: World, L: Layout): Beat {
  const [sent] = w.rows;
  return {
    still: 1.9,
    seq: [
      [sent, { dy: 26 * L.k, o: 0 }, { duration: 0.01, at: 0 }],
      [w.capsule, { o: 0 }, { duration: 0.35, at: 0.05 }],
      [w.PL, bodyL(L), { duration: 1.0, ease: flow, at: 0.1 }],
      [w.PR, bodyR(L), { duration: 1.0, ease: flow, at: 0.1 }],
      [w.env, { panel: 1 }, { duration: 1.0, ease: flow, at: 0.1 }],
      [w.A, headL(L), { duration: 0.9, ease: flow, at: 0.15 }],
      [w.B, headR(L), { duration: 0.9, ease: flow, at: 0.2 }],
      [w.env, { contour: 0.3 }, { duration: 0.8, at: 0.3 }],
      home(w, L, 0.4),
      [sent, { dy: 0, o: 1 }, { duration: 0.55, ease: settle, at: 0.55 }],
      ...land(w, L, 1, 1.0),
      ...arrive(w, 1, 1.35),
    ],
  };
}
/** Beat 3: a tendril reaches each passage, the membrane closes round it, tugs it a little, and what it says
 * streams into the body and settles on its row. Then the passage is let go and floats on. */
function find(w: World, L: Layout, sizes: Size[]): Beat {
  const k = L.k;
  const one = (S: Strand, K: Cell, U: Cell, slot: number, row: number, t: number): AnimationSequence => {
    const n = w.nodes[slot], M = L.slots[slot], P = L.rims[slot], R = L.rows[row], pk = pocket(sizes[slot], k, M);
    const tug = { x: M.x + (P.x - M.x) * 0.18, y: M.y + (P.y - M.y) * 0.18 };
    return [
      lookAt(w, M, t + 0.05),
      [S, { ax: P.x, ay: P.y, bx: P.x, by: P.y, r: 9 * k, taper: 0.35, tone: 1 }, { duration: 0.01, at: t }],
      [S, { bx: M.x, by: M.y }, { duration: 0.7, ease: out, at: t + 0.02 }],
      [n, { free: 0 }, { duration: 0.3, at: t + 0.6 }],
      [K, { px: M.x, py: M.y, ...zero, r: pk.r, tone: 1, w: 1.3, rot: 0 }, { duration: 0.01, at: t + 0.72 }],
      [K, { hw: pk.hw, hh: pk.hh }, { ...spring(210, 14), at: t + 0.75 }],
      [n, { flash: 1 }, { duration: 0.1, at: t + 0.75 }],
      [n, { flash: 0 }, { duration: 0.4, ease: out, at: t + 0.85 }],
      [n, { s: 1.1 }, { duration: 0.14, ease: out, at: t + 0.75 }],
      [n, { s: 1 }, { duration: 0.3, at: t + 0.89 }],
      [[n, K], { px: tug.x, py: tug.y }, { duration: 0.5, ease: inOut, at: t + 1.0 }],
      [S, { bx: tug.x, by: tug.y }, { duration: 0.5, ease: inOut, at: t + 1.0 }],
      [U, { px: tug.x, py: tug.y, ...zero, r: 5 * k, tone: 1, w: 1.3, rot: 0 }, { duration: 0.01, at: t + 1.45 }],
      [U, { hw: 6 * k, hh: 6 * k }, { duration: 0.15, at: t + 1.47 }],
      [S, { r: 12 * k }, { duration: 0.3, at: t + 1.5 }],
      [n, { s: 0.9 }, { duration: 0.5, at: t + 1.5 }],
      [U, { px: P.x, py: P.y }, { duration: 0.6, ease: inOut, at: t + 1.62 }],
      [U, { hw: 9 * k, hh: 9 * k, r: 9 * k }, { duration: 0.15, at: t + 2.22 }],
      [w.env, { pulse: 1 }, { duration: 0.12, at: t + 2.22 }],
      [w.env, { pulse: 0 }, { duration: 0.35, at: t + 2.34 }],
      [U, { px: R.x, py: R.y }, { duration: 0.4, ease: inOut, at: t + 2.45 }],
      [U, zero, { duration: 0.25, at: t + 2.85 }],
      [K, zero, { duration: 0.35, at: t + 2.3 }],
      [S, { r: 8 * k }, { duration: 0.2, at: t + 2.3 }],
      [S, { bx: P.x, by: P.y, taper: 0.9 }, { duration: 0.5, ease: inOut, at: t + 2.5 }],
      [S, { r: 0 }, { duration: 0.2, at: t + 2.95 }],
      [n, { px: M.x, py: M.y, s: 1 }, { ...spring(120, 12), at: t + 2.4 }],
      [n, { free: 1 }, { duration: 0.5, at: t + 2.6 }],
      ...land(w, L, row, t + 2.5),
      ...arrive(w, row, t + 2.9),
    ];
  };
  const seq = story.passages.flatMap((_, i) => one(w.strands[i], w.K[i], w.U[i], i, 2 + i, i * 0.6));
  return { still: 2.2, seq: [...seq, ...widen(w, 0.8, 1.2), home(w, L, 2.9 + PASSAGES * 0.6)] };
}
/** Beat 4: the answer types itself; a second look runs along it and approves; the check lands. */
function answer(w: World, L: Layout): Beat {
  const k = L.k, [K0] = w.K, R = L.reply;
  return {
    still: 3.6,
    seq: [
      [w.rows[REPLY], { dy: 8 * k }, { duration: 0.01, at: 0 }],
      [w.rows[REPLY], { o: 1, dy: 0 }, { duration: 0.4, ease: settle, at: 0 }],
      [w.lines, { typing: 1 }, { duration: 0.3, at: 0.1 }],
      [w.eyes[0], { lid: 0.35 }, { duration: 0.3, at: 0.2 }],
      lookAt(w, { x: R.x + R.w / 2, y: R.y + R.h / 2 }, 0.2),
      [w.lines, { typing: 0 }, { duration: 0.25, at: 1.0 }],
      [w.eyes[0], { lid: 0 }, { duration: 0.3, at: 1.1 }],
      [w.lines, { a: 1 }, { duration: 1.3, ease: out, at: 1.1 }],
      [K0, { px: R.x + R.w - 8, py: R.y + R.h + 2, ...zero, tone: 3, w: 1.4, rot: 0 }, { duration: 0.01, at: 2.45 }],
      [K0, { hw: 7 * k, hh: 7 * k, r: 7 * k }, { duration: 0.15, at: 2.5 }],
      [K0, { px: R.x + 8 }, { duration: 0.9, ease: inOut, at: 2.65 }],
      [K0, zero, { duration: 0.2, at: 3.55 }],
      [w.lines, { check: 1 }, { duration: 0.3, at: 3.4 }],
      ...blink(w, 3.45),
      ...land(w, L, CHECK, 3.6),
      ...arrive(w, CHECK, 3.9),
      home(w, L, 4.0),
    ],
  };
}
function buildBeat(beat: number, w: World, L: Layout, sizes: Size[]): Beat | null {
  switch (beat) {
    case 1: return bond(w, L);
    case 2: return launch(w, L);
    case 3: return find(w, L, sizes);
    case 4: return answer(w, L);
    case LAST: return { still: 0.5, seq: [...blink(w, 0.1), home(w, L, 0.1)] };
    default: return null;
  }
}

/* ── One play-through of the story, painted over the hero ── */

type StoryProps = { hero: HTMLElement; stage: HTMLElement; moving: boolean; quiet: boolean; mode: Mode; onReady: () => void; controls: React.ReactNode };

function Story({ hero, stage, moving, quiet, mode, onReady, controls: bar }: StoryProps) {
  const [beat, setBeat] = React.useState(0);
  const [typed, setTyped] = React.useState("");
  const [ready, setReady] = React.useState(0);
  const [compact, setCompact] = React.useState(false);
  const capsule = React.useRef<HTMLDivElement>(null), panel = React.useRef<HTMLDivElement>(null), theatre = React.useRef<HTMLDivElement>(null);
  const membrane = React.useRef<MembraneHandle>(null);
  const eyeRefs = React.useRef<(HTMLSpanElement | null)[]>([]), nodeRefs = React.useRef<(HTMLSpanElement | null)[]>([]);
  const rowRefs = React.useRef<(HTMLElement | null)[]>([]), reply = React.useRef<HTMLDivElement | null>(null);
  const origins = React.useRef<number[]>([]); // each thing's blob centre from its left edge, measured once a layout
  const world = React.useRef(createWorld()), roam = React.useRef(createRoam()), layout = React.useRef<Layout | null>(null);
  const capture = React.useRef<Capture | null>(null), controls = React.useRef<AnimationPlaybackControls | null>(null), generation = React.useRef(0);
  const clock = React.useRef(0), pointer = React.useRef<Point | null>(null);
  const typing = React.useRef<{ at: number; n: number } | null>(null), started = React.useRef(false), readyOnce = React.useRef(false);
  const scene = React.useRef({
    cells: Array.from({ length: 16 }, (): MembraneCell => ({ x: 0, y: 0, hw: 0, hh: 0, r: 0, tone: 0, rot: 0, w: 1 })),
    strands: Array.from({ length: 8 }, (): MembraneStrand => ({ ax: 0, ay: 0, bx: 0, by: 0, r: 0, tone: 0, taper: 0, w: 1 })),
  });
  const state = React.useRef({ moving, quiet, beat });
  React.useLayoutEffect(() => {
    state.current = { moving, quiet, beat };
  }, [moving, quiet, beat]);
  const rowRef = React.useMemo(() => {
    const refs = Array.from({ length: ROWS }, (_, i) => (el: HTMLElement | null) => { rowRefs.current[i] = el; });
    return (i: number) => refs[i];
  }, []);
  const replyRef = React.useCallback((el: HTMLDivElement | null) => { reply.current = el; }, []);

  /* Steering for one free organism: wander with arrival, keep company, keep off the capsule. */
  const stepRoam = React.useCallback((i: number, dt: number, L: Layout) => {
    const R = roam.current, r = R[i], k = L.k, F = L.field, cap = capture.current;
    if (cap) {
      const tc = clock.current - cap.t0, dock = L.docks[i], from = cap.from[i], startAt = 0.28 + i * 0.07;
      if (tc >= 1.3) {
        Object.assign(r, { x: dock.x, y: dock.y, vx: 0, vy: 0 });
        return;
      }
      if (tc < startAt) {
        const dx = dock.x - from.x, dy = dock.y - from.y, d = Math.hypot(dx, dy) || 1, pull = (i < 2 ? 22 : 12) * k;
        damp(r, from.x - (dx / d) * pull, from.y - (dy / d) * pull, 0.18, dt);
      } else damp(r, dock.x, dock.y, i < 2 ? 0.22 : 0.2, dt);
      return;
    }
    r.wait -= dt;
    let dx = r.tx - r.x, dy = r.ty - r.y, d = Math.hypot(dx, dy);
    const b = L.bounds;
    if (r.wait <= 0 || d < 18 * k) {
      if (Math.random() < 0.4) {
        const a = Math.random() * Math.PI * 2;
        r.tx = F.cx + Math.cos(a) * (F.hw + 70 * k + Math.random() * 90 * k);
        r.ty = F.cy + Math.sin(a) * (F.hh + 60 * k + Math.random() * 70 * k);
      } else {
        r.tx = b.x0 + Math.random() * (b.x1 - b.x0);
        r.ty = b.y0 + Math.random() * (b.y1 - b.y0);
      }
      r.tx = Math.min(b.x1, Math.max(b.x0, r.tx));
      r.ty = Math.min(b.y1, Math.max(b.y0, r.ty));
      r.wait = 2.5 + Math.random() * 4;
      dx = r.tx - r.x; dy = r.ty - r.y; d = Math.hypot(dx, dy) || 1;
    }
    const maxS = (i < 2 ? 36 : 48) * k * (0.85 + (0.3 * ((i * 7) % 5)) / 5), maxF = (i < 2 ? 60 : 80) * k, arrival = Math.min(1, d / (140 * k));
    let fx = (dx / d) * maxS * arrival - r.vx, fy = (dy / d) * maxS * arrival - r.vy;
    const fm = Math.hypot(fx, fy);
    if (fm > maxF) { fx *= maxF / fm; fy *= maxF / fm; }
    for (let j = 0; j < ORGANISMS; j++) {
      if (j === i) continue;
      const ex = r.x - R[j].x, ey = r.y - R[j].y, dd = Math.hypot(ex, ey) || 1, minD = r.r + R[j].r + 30 * k;
      if (dd < minD) { fx += (ex / dd) * (minD - dd) * 4; fy += (ey / dd) * (minD - dd) * 4; }
    }
    const kx = F.hw + 30 * k - Math.abs(r.x - F.cx), ky = F.hh + 26 * k - Math.abs(r.y - F.cy);
    if (kx > 0 && ky > 0) {
      if (kx < ky) fx += Math.sign(r.x - F.cx || 1) * kx * 6;
      else fy += Math.sign(r.y - F.cy || 1) * ky * 6;
    }
    if (r.x < b.x0) fx += (b.x0 - r.x) * 5;
    if (r.x > b.x1) fx += (b.x1 - r.x) * 5;
    if (r.y < b.y0) fy += (b.y0 - r.y) * 5;
    if (r.y > b.y1) fy += (b.y1 - r.y) * 5;
    r.vx += fx * dt; r.vy += fy * dt; r.x += r.vx * dt; r.y += r.vy * dt;
  }, []);

  /* Paint one frame: the membrane, then the DOM that rides on it. */
  const paint = React.useCallback((delta: number) => {
    const w = world.current, L = layout.current, m = membrane.current;
    if (!L || !m) return;
    const { moving: live, quiet: still } = state.current;
    const dt = live && !still ? Math.min(delta, 40) / 1000 : 0;
    clock.current += dt;
    const t = clock.current, k = L.k, f = w.env.free, p = pointer.current, R = roam.current;
    if (f > 0) for (let i = 0; i < ORGANISMS; i++) stepRoam(i, dt, L);
    // The page types the question on the same clock, so a pause pauses the typing too.
    const ty = typing.current;
    if (ty) {
      const n = Math.min(story.question.length, Math.floor((t - ty.at) / 0.03));
      if (n !== ty.n) { ty.n = n; setTyped(story.question.slice(0, n)); }
      if (n === story.question.length && t - ty.at > 0.03 * n + 0.45) { typing.current = null; setBeat(1); }
    }
    const breath = 1 + w.env.breath * 0.012 * Math.sin(t * 1.9), pulse = w.env.pulse * 3 * k;
    const cells = scene.current.cells;
    const put = (i: number, c: Cell, x = c.px, y = c.py, hw = c.hw, hh = c.hh, r = c.r, rot = c.rot) => Object.assign(cells[i], { x, y, hw, hh, r, tone: c.tone, rot, w: c.w });
    const lean = (r: Roam) => {
      if (!p || f <= 0 || capture.current) return { x: 0, y: 0 };
      const dx = p.x - r.x, dy = p.y - r.y, d = Math.hypot(dx, dy);
      if (d > 150 * k || d < 1) return { x: 0, y: 0 };
      const a = (1 - d / (150 * k)) * 9 * k * f;
      return { x: (dx / d) * a, y: (dy / d) * a };
    };
    const pos: Point[] = [];
    [w.A, w.B, ...w.O].forEach((c, i) => {
      const r = R[i], sp = Math.hypot(r.vx, r.vy), e = Math.min(0.32, sp / (110 * k)), ang = sp > 1 ? Math.atan2(r.vy, r.vx) : 0, l = lean(r), bob = Math.sin(t * 1.1 + r.seed) * 3 * k;
      const x = c.px + (r.x + l.x - c.px) * f, y = c.py + (r.y + l.y + bob - c.py) * f;
      const hw = (c.hw + (r.r * (1 + e) - c.hw) * f) * breath, hh = (c.hh + (r.r * (1 - e * 0.5) - c.hh) * f) * breath, rr = c.r + (r.r - c.r) * f;
      pos[i] = { x, y };
      put(i, c, x, y, hw, hh, rr, f > 0 ? ang : c.rot);
    });
    put(6, w.PL, w.PL.px, w.PL.py, w.PL.hw, w.PL.hh * breath + pulse);
    put(7, w.PR, w.PR.px, w.PR.py, w.PR.hw, w.PR.hh * breath + pulse);
    w.K.forEach((c, i) => put(8 + i, c));
    w.U.slice(0, 4).forEach((c, i) => put(12 + i, c));
    const strands = scene.current.strands;
    w.strands.forEach((s, i) => Object.assign(strands[i], s));
    // Curious pseudopods: the two leads probe toward the capsule while free.
    const probe = (i: number, from: Point, target: Point, phase: number) => {
      const s = strands[6 + i], amount = (capture.current ? 0 : f) * Math.pow(Math.max(0, Math.sin(t * 0.8 + phase)), 3);
      const dx = target.x - from.x, dy = target.y - from.y, d = Math.hypot(dx, dy) || 1;
      Object.assign(s, { ax: from.x, ay: from.y, bx: from.x + (dx / d) * 46 * k * amount, by: from.y + (dy / d) * 46 * k * amount, r: 9 * k * amount, taper: 0.7, tone: i ? 2 : 0, w: 1 });
    };
    probe(0, pos[0], { x: L.endL.x + 40 * k, y: L.field.cy }, 0);
    probe(1, pos[1], { x: L.endR.x - 40 * k, y: L.field.cy }, 2.4);
    m.draw({ cells, strands, blend: 24 * k + 4, wobble: still ? 0 : w.env.wobble, contour: w.env.contour, time: t });
    // The eyes look at the gaze target, or at the pointer while free.
    const gazeTo = (from: Point) => {
      const target = w.gaze.w > 0.5 ? { x: w.gaze.px, y: w.gaze.py } : (p ?? { x: L.field.cx, y: L.field.cy });
      const dx = target.x - from.x, dy = target.y - from.y, d = Math.hypot(dx, dy) || 1, a = Math.min(1, d / 80) * 3.5 * k;
      return { x: (dx / d) * a, y: (dy / d) * a };
    };
    w.eyes.forEach((e, i) => {
      const el = eyeRefs.current[i];
      if (!el) return;
      const g = gazeTo(pos[i]);
      el.style.transform = `translate(${(pos[i].x + g.x).toFixed(1)}px,${(pos[i].y + g.y - 2 * k).toFixed(1)}px)`;
      el.style.opacity = String(e.o);
      el.style.setProperty("--lid", e.lid.toFixed(3));
    });
    // Things drift while free; a held thing sits where the tendril has it, anchored at its blob.
    w.nodes.forEach((n, i) => {
      const el = nodeRefs.current[i];
      if (!el) return;
      const drift = (still ? 0 : n.free) * (L.roomy ? 1 : 0.6);
      const ox = (Math.sin(t * 0.5 + i * 1.3) * 13 + Math.sin(t * 0.21 + i * 0.7) * 7) * k * drift * (L.roomy ? 1 : 0.35);
      const oy = (Math.cos(t * 0.38 + i * 0.9) * 4 + Math.cos(t * 0.17 + i) * 2) * k * drift;
      const gx = origins.current[i] ?? 0;
      el.style.transform = `translate(${(n.px + ox - gx).toFixed(1)}px,${(n.py + oy).toFixed(1)}px) translateY(-50%) rotate(${(Math.sin(t * 0.3 + i) * 4 * drift).toFixed(2)}deg) scale(${n.s.toFixed(3)})`;
      el.style.opacity = String(n.o);
      el.style.setProperty("--t", n.t.toFixed(3));
      el.style.setProperty("--rip", n.rip.toFixed(3));
      el.style.setProperty("--flash", n.flash.toFixed(3));
    });
    w.rows.forEach((r, i) => {
      const el = rowRefs.current[i];
      if (!el) return;
      el.style.opacity = String(r.o);
      el.style.setProperty("--dy", `${r.dy.toFixed(1)}px`);
      el.style.setProperty("--p", r.p.toFixed(3));
      el.style.setProperty("--g", r.g.toFixed(3));
      const hidden = r.o < 0.5;
      if (el.inert !== hidden) {
        el.inert = hidden;
        el.setAttribute("aria-hidden", hidden ? "true" : "false");
      }
    });
    const bubble = reply.current;
    if (bubble) {
      bubble.style.setProperty("--la", w.lines.a.toFixed(3));
      bubble.style.setProperty("--check", w.lines.check.toFixed(3));
      bubble.style.setProperty("--typing", w.lines.typing.toFixed(3));
    }
    if (capsule.current) {
      capsule.current.style.opacity = String(w.capsule.o);
      capsule.current.style.setProperty("--line", w.env.underline.toFixed(3));
    }
    if (panel.current) {
      const el = panel.current, open = w.env.panel > 0.5;
      el.style.opacity = String(w.env.panel);
      if ((el.dataset.open === "true") !== open) {
        el.dataset.open = open ? "true" : "false";
        el.inert = !open;
      }
    }
  }, [stepRoam]);

  /* One clock, painting after Motion's own render step, so seeks and completions are already written. */
  const paintSoon = React.useCallback((frames = 4) => {
    let left = frames;
    const tick = () => {
      paint(0);
      if (--left <= 0) cancelFrame(tick);
    };
    frame.postRender(tick, true);
  }, [paint]);
  React.useEffect(() => {
    const tick = ({ delta }: { delta: number }) => paint(delta);
    if (moving && !quiet) {
      frame.postRender(tick, true);
      return () => cancelFrame(tick);
    }
    paintSoon();
  }, [moving, quiet, paint, paintSoon, beat, ready]);

  /* Layout follows the real capsule, panel and rows; the pose of the current beat is re-fitted on resize. */
  const relayout = React.useCallback(() => {
    if (!capsule.current || !panel.current) return;
    const heads = [hero.querySelector(".hero-title"), hero.querySelector(".hero-lead")].filter((el): el is Element => el !== null);
    const L = measure(hero, capsule.current, panel.current, rowRefs.current, reply.current, heads);
    if (!L) return;
    layout.current = L;
    setCompact(!L.roomy);
    const w = world.current, b = state.current.beat;
    if (b === 0) restPose(w, L, roam.current);
    else if (b === 1) bondedPose(w, L, roam.current);
    else panelPose(w, L, roam.current, b);
    setReady((v) => v + 1);
  }, [hero]);
  React.useEffect(() => {
    const box = theatre.current;
    if (!box) return;
    let size = "";
    const observer = new ResizeObserver(() => {
      const next = `${box.offsetWidth}x${box.offsetHeight}`;
      if (next === size) return;
      size = next;
      relayout();
    });
    observer.observe(box);
    document.fonts?.ready.then(relayout);
    return () => observer.disconnect();
  }, [relayout]);
  /* Each thing's side, then one read of where its blob sits: the paint loop only writes. */
  React.useLayoutEffect(() => {
    const L = layout.current;
    if (!L) return;
    nodeRefs.current.forEach((el, i) => {
      if (el) el.dataset.side = L.slots[i].x < L.W / 2 ? "left" : "right";
    });
    origins.current = nodeRefs.current.map((el) => {
      const shape = el?.firstElementChild as HTMLElement | null;
      return shape ? shape.offsetLeft + shape.offsetWidth / 2 : 0;
    });
    nodeRefs.current.forEach((el, i) => {
      if (el) el.style.transformOrigin = `${origins.current[i].toFixed(1)}px 50%`;
    });
  }, [ready, compact]);
  React.useEffect(() => {
    if (ready && !readyOnce.current) {
      readyOnce.current = true;
      onReady();
    }
  }, [ready, onReady]);

  /* The page types the question soon after the hero is ready, then the story runs on its own. */
  React.useEffect(() => {
    if (!ready || started.current || !moving || quiet) return;
    const timer = window.setTimeout(() => {
      started.current = true;
      typing.current = { at: clock.current, n: 0 };
    }, START_MS);
    return () => window.clearTimeout(timer);
  }, [ready, moving, quiet]);

  /* Build the current beat's timeline; play, pause or seek according to the motion gates. */
  React.useEffect(() => {
    const L = layout.current, w = world.current;
    controls.current?.stop();
    controls.current = null;
    if (!L) return;
    if (beat === 1) {
      // The organisms fly in from wherever they are; the heads' tween targets are their docks.
      if (!capture.current) capture.current = { t0: clock.current, from: roam.current.map((r) => ({ x: r.x, y: r.y })) };
      [w.A, w.B, ...w.O].forEach((c, i) => Object.assign(c, at(L.docks[i])));
      if (quiet || !moving) roam.current.forEach((r, i) => Object.assign(r, { x: L.docks[i].x, y: L.docks[i].y, vx: 0, vy: 0 }));
    } else capture.current = null;
    const sizes = nodeRefs.current.map((el): Size => {
      const shape = el?.firstElementChild as HTMLElement | null;
      return { w: shape?.offsetWidth ?? 30, h: shape?.offsetHeight ?? 30 };
    });
    if (beat === LAST) panelPose(w, L, roam.current, LAST);
    const built = buildBeat(beat, w, L, sizes);
    if (!built) {
      if (beat === 0) restPose(w, L, roam.current);
      return;
    }
    const own = ++generation.current;
    let cancelled = false;
    const c = animate(built.seq, { defaultTransition: { ease: "easeInOut" } });
    controls.current = c;
    if (quiet || !moving) {
      c.pause();
      c.time = quiet ? built.still : 0;
    }
    c.finished.then(
      () => {
        if (cancelled || generation.current !== own || !state.current.moving || state.current.quiet) return;
        c.complete();
        setBeat((b) => Math.min(LAST, b + 1));
      },
      () => {},
    );
    return () => {
      cancelled = true;
      if (controls.current === c) {
        c.stop();
        controls.current = null;
      }
    };
    // A beat's timeline is rebuilt for a new beat, a new layout or a change in quiet; `moving` plays or pauses it below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [beat, ready, quiet]);
  React.useEffect(() => {
    const c = controls.current;
    if (!c || quiet) return;
    if (moving) c.play();
    else c.pause();
  }, [moving, quiet]);
  React.useEffect(() => {
    const move = (event: PointerEvent) => {
      const s = hero.getBoundingClientRect();
      pointer.current = { x: event.clientX - s.left, y: event.clientY - s.top };
    };
    const leave = () => { pointer.current = null; };
    hero.addEventListener("pointermove", move);
    hero.addEventListener("pointerleave", leave);
    return () => {
      hero.removeEventListener("pointermove", move);
      hero.removeEventListener("pointerleave", leave);
    };
  }, [hero]);

  const cue = beats[beat].cue;
  return (
    <>
      {createPortal(
        <div className="pb-stage" data-compact={compact} data-quiet={quiet} data-moving={moving}>
          <Membrane ref={membrane} mode={mode} onMeasure={relayout} />
          <div className="pb-riders">
            {RADII.map((_, i) => (
              <span key={i} className="pb-eyes" data-small={i > 1} ref={(el) => { eyeRefs.current[i] = el; }}>
                <i />
                <i />
              </span>
            ))}
            {ENV.map((thing, i) => (
              <span key={i} className="pb-thing" data-kind={thing?.kind ?? "filing"} data-empty={!thing} ref={(el) => { nodeRefs.current[i] = el; }}>
                <span className="pb-thing-shape">
                  <i className="pb-thing-ring" />
                  <i className="pb-thing-flash" />
                  <Icon name={thing?.icon ?? "file"} />
                </span>
                <span className="pb-thing-label">
                  <em>{thing ? KIND_TITLE[thing.kind] : ""}</em>
                  <b>{thing?.title ?? ""}</b>
                  <small>{thing?.sub ?? ""}</small>
                </span>
              </span>
            ))}
          </div>
        </div>,
        stage,
      )}
      <div className="story-live" ref={theatre} data-beat={beat} data-moving={moving} data-quiet={quiet} role="group" aria-label="The saved answer's story, moving">
        <div className="pb-panel" ref={panel} data-open="false">
          <StoryPanel story={story} prefix="hero-live-" rowRef={rowRef} replyRef={replyRef} />
        </div>
        <div className="pb-capsule" ref={capsule} aria-hidden="true">
          <span className="pb-prefix">›</span>
          <span className="pb-typed">{typed}</span>
          <span className="pb-send">
            <Icon name="arrow-right" />
          </span>
        </div>
      </div>
      <div className="story-caption">
        <TextReveal text={cue} moving={moving && !quiet} />
        <div className="pb-progress" role="img" aria-label={`Story: ${beats[beat].label}`}>
          {beats.slice(1, LAST).map((b, i) => (
            <span key={b.label} data-complete={beat > i + 1} data-current={beat === i + 1} />
          ))}
        </div>
        {bar}
      </div>
    </>
  );
}

/* ── The field and the headline's weights: Prompt Bond's ShaderGradient, and its variable proximity ── */

class FieldBoundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(error: Error) {
    console.warn("Hero field unavailable; the still image stays.", error);
  }
  render() {
    return this.state.failed ? null : this.props.children;
  }
}
type FieldProps = { mode: Mode; moving: boolean };

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

/* ── The moving hero: finds its places in the still hero, runs the story, then brings in the field ── */

export function HeroLive() {
  const anchor = React.useRef<HTMLSpanElement>(null);
  const [hero, setHero] = React.useState<HTMLElement | null>(null);
  const [Field, setField] = React.useState<React.ComponentType<FieldProps> | null>(null);
  const [paused, setPaused] = React.useState(false);
  const [replay, setReplay] = React.useState(0);
  const mode = useMode();
  const { enabled, inView } = useMotionVisibility(hero);
  const moving = enabled && inView && !paused;

  React.useLayoutEffect(() => {
    setHero(anchor.current?.closest<HTMLElement>(".hero") ?? null);
  }, []);
  useProximity(hero, moving);

  const onReady = React.useCallback(() => {
    if (!hero) return;
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
      <button type="button" className="pb-control" onClick={() => setReplay((n) => n + 1)}>
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
        <Story key={replay} hero={hero} stage={stage} moving={moving} quiet={!enabled} mode={mode} onReady={onReady} controls={bar} />
      )}
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

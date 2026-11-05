// The FilingLens mark, variant #6 of the logo sheet: two arcs make a lens and one bar crosses it, the site's
// accent inside the lens and ink outside it, sticking out on both sides. Every stroke is STROKE wide with round
// ends, every gap between two strokes is GAP, and the bar breaks where the arcs' circle would cross it.
import { createElement } from "react";

export const STROKE = 4;
export const GAP = 3;
export const RADIUS = 12; // the arcs' circle, through the strokes' centres: arcs end 36° above the bar
const PILL = 3; // an ink pill's length between the centres of its round ends

const round = (n: number) => Number(n.toFixed(3));
const endY = STROKE + GAP; // an arc's end clears the bar by GAP
const barEnd = RADIUS - GAP / 2 - STROKE / 2;
const inkStart = RADIUS + GAP / 2 + STROKE / 2;

/** The centres of the round ends, right and below the middle; the mark is symmetric on both axes. */
export const POINTS = {
  arcEnd: { x: round(Math.sqrt(RADIUS ** 2 - endY ** 2)), y: endY },
  barEnd,
  inkStart,
  inkEnd: inkStart + PILL,
};
/** Half the mark's width and height, round ends included. */
export const HALF = { width: POINTS.inkEnd + STROKE / 2, height: RADIUS + STROKE / 2 };

const { arcEnd: a, inkEnd } = POINTS;
const arc = (x: number, y: number) => `M${-x} ${y}A${RADIUS} ${RADIUS} 0 0 1 ${x} ${y}`;
export const INK_PATH = `${arc(a.x, -a.y)}${arc(-a.x, a.y)}M${-inkEnd} 0H${-inkStart}M${inkStart} 0H${inkEnd}`;
export const BAR_PATH = `M${-barEnd} 0H${barEnd}`;

/** The site's ink and accent; the light mark's bar reaches 7.0:1 on the paper, the dark one's 8.8:1. */
export const COLORS = {
  light: { ink: "#1A1D22", bar: "#4A5563" },
  dark: { ink: "#E6E8EB", bar: "#A9B4C2" },
} as const;

type Paint = { ink: string; bar: string };
const ROOT = `fill="none" stroke-width="${STROKE}" stroke-linecap="round"`;
const BOX = { wide: "-21.5 -15 43 30", square: "-21.5 -21.5 43 43" };

/** The mark as SVG text: `wide` fits it, with a unit of air; `square` centres it for icons. */
export function markSvg(paint: Paint, shape: keyof typeof BOX = "wide"): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${BOX[shape]}" ${ROOT}><path stroke="${paint.ink}" d="${INK_PATH}"/><path stroke="${paint.bar}" d="${BAR_PATH}"/></svg>`;
}

/** The app icon as ImageResponse draws it: the dark mark, `share` of the side wide, on a graphite tile whose
    corners `round` (a share of the side) rounds; the home screen's (app/apple-icon.tsx) stays square, as iOS
    rounds it, and favicon.ico's (scripts/favicon.mjs) takes a wider mark, so it still reads at 16 px. */
export function appIcon(side: number, { share = 132 / 180, round = 0 } = {}) {
  const mark = `data:image/svg+xml,${encodeURIComponent(markSvg(COLORS.dark, "square"))}`;
  const tile = { width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" };
  const box = Math.round(side * share);
  return createElement(
    "div",
    { style: { ...tile, background: COLORS.light.ink, ...(round && { borderRadius: side * round }) } },
    createElement("img", { src: mark, width: box, height: box, alt: "" }),
  );
}

/** The favicon: the square light mark, and the dark one in a dark browser. */
export function faviconSvg(): string {
  const { light, dark } = COLORS;
  const style = `.i{stroke:${light.ink}}.t{stroke:${light.bar}}@media (prefers-color-scheme: dark){.i{stroke:${dark.ink}}.t{stroke:${dark.bar}}}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${BOX.square}" ${ROOT}><style>${style}</style><path class="i" d="${INK_PATH}"/><path class="t" d="${BAR_PATH}"/></svg>`;
}

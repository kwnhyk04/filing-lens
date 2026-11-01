// The FilingLens mark, variant #6 of the logo sheet: two arcs make a lens and one bar crosses it, teal
// inside the lens and ink outside it, sticking out on both sides. Every stroke is STROKE wide with round
// ends, every gap between two strokes is GAP, and the bar breaks where the arcs' circle would cross it.
export const STROKE = 4;
export const GAP = 3;
export const RADIUS = 12; // the arcs' circle, through the strokes' centres: arcs end 36° above the bar
const PILL = 3; // an ink pill's length between the centres of its round ends

const round = (n: number) => Number(n.toFixed(3));
const endY = STROKE + GAP; // an arc's end clears the bar by GAP
const tealEnd = RADIUS - GAP / 2 - STROKE / 2;
const inkStart = RADIUS + GAP / 2 + STROKE / 2;

/** The centres of the round ends, right and below the middle; the mark is symmetric on both axes. */
export const POINTS = {
  arcEnd: { x: round(Math.sqrt(RADIUS ** 2 - endY ** 2)), y: endY },
  tealEnd,
  inkStart,
  inkEnd: inkStart + PILL,
};
/** Half the mark's width and height, round ends included. */
export const HALF = { width: POINTS.inkEnd + STROKE / 2, height: RADIUS + STROKE / 2 };

const { arcEnd: a, inkEnd } = POINTS;
const arc = (x: number, y: number) => `M${-x} ${y}A${RADIUS} ${RADIUS} 0 0 1 ${x} ${y}`;
export const INK_PATH = `${arc(a.x, -a.y)}${arc(-a.x, a.y)}M${-inkEnd} 0H${-inkStart}M${inkStart} 0H${inkEnd}`;
export const TEAL_PATH = `M${-tealEnd} 0H${tealEnd}`;

/** The light mark's teal reaches 3.5:1 on the paper, a graphic's 3:1; the dark one's 9.3:1 on navy. */
export const COLORS = {
  light: { ink: "#0F1B2D", teal: "#0D9488" },
  dark: { ink: "#FAF8F3", teal: "#2DD4BF" },
} as const;

type Paint = { ink: string; teal: string };
const ROOT = `fill="none" stroke-width="${STROKE}" stroke-linecap="round"`;
const BOX = { wide: "-21.5 -15 43 30", square: "-21.5 -21.5 43 43" };

/** The mark as SVG text: `wide` fits it, with a unit of air; `square` centres it for icons. */
export function markSvg(paint: Paint, shape: keyof typeof BOX = "wide"): string {
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${BOX[shape]}" ${ROOT}><path stroke="${paint.ink}" d="${INK_PATH}"/><path stroke="${paint.teal}" d="${TEAL_PATH}"/></svg>`;
}

/** The favicon: the square light mark, and the dark one in a dark browser. */
export function faviconSvg(): string {
  const { light, dark } = COLORS;
  const style = `.i{stroke:${light.ink}}.t{stroke:${light.teal}}@media (prefers-color-scheme: dark){.i{stroke:${dark.ink}}.t{stroke:${dark.teal}}}`;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${BOX.square}" ${ROOT}><style>${style}</style><path class="i" d="${INK_PATH}"/><path class="t" d="${TEAL_PATH}"/></svg>`;
}

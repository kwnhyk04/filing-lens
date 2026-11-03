// Draws app/favicon.ico from lib/logo.ts: the app icon at 16, 32 and 48 px, for browsers that take no SVG icon.
// Run `node scripts/favicon.mjs` after the mark changes; scripts/favicon.test.mjs fails until then.
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { ImageResponse } from "next/og.js"; // plain Node needs the file; Next's bundler resolves "next/og"

import { appIcon } from "../lib/logo.ts";

const SIDES = [16, 32, 48];

/** One frame, a PNG: the tile rounded, the mark wider than the home screen's so it still reads at 16 px. */
async function frame(side) {
  const icon = appIcon(side, { share: 0.875, round: 0.1875 });
  return Buffer.from(await new ImageResponse(icon, { width: side, height: side }).arrayBuffer());
}

/** The ICO: its header, an entry per frame (size, planes, bits a pixel, length, offset), then the PNG frames. */
export async function favicon() {
  const frames = await Promise.all(SIDES.map(frame));
  const head = Buffer.alloc(6 + 16 * frames.length);
  head.writeUInt16LE(1, 2); // an icon, not a cursor
  head.writeUInt16LE(frames.length, 4);
  let offset = head.length;
  frames.forEach((png, i) => {
    const entry = 6 + 16 * i;
    head[entry] = head[entry + 1] = SIDES[i];
    head.writeUInt16LE(1, entry + 4);
    head.writeUInt16LE(32, entry + 6);
    head.writeUInt32LE(png.length, entry + 8);
    head.writeUInt32LE(offset, entry + 12);
    offset += png.length;
  });
  return Buffer.concat([head, ...frames]);
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  writeFileSync(new URL("../app/favicon.ico", import.meta.url), await favicon());
}

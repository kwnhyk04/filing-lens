// The app icon a phone's home screen shows: the dark mark on ink navy, drawn from lib/logo.ts at build time.
import { ImageResponse } from "next/og";

import { COLORS, markSvg } from "../lib/logo.ts";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  const mark = `data:image/svg+xml,${encodeURIComponent(markSvg(COLORS.dark, "square"))}`;
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#0F1B2D" }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- ImageResponse draws plain img elements */}
        <img src={mark} width={132} height={132} alt="" />
      </div>
    ),
    size,
  );
}

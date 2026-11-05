// The app icon a phone's home screen shows: the dark mark on graphite, drawn from lib/logo.ts at build time.
import { ImageResponse } from "next/og";

import { appIcon } from "../lib/logo.ts";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(appIcon(size.width), size);
}

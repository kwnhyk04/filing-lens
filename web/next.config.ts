import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

// The repo root, since web imports ../clients/ts.
const root = fileURLToPath(new URL("..", import.meta.url));

const config: NextConfig = {
  poweredByHeader: false,
  turbopack: { root, rules: { "*.md": { type: "text" } } }, // the landing page reads the eval report's table
  outputFileTracingRoot: root,
  async headers() {
    const headers = [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), browsing-topics=()" },
    ];
    return [{ source: "/:path*", headers }];
  },
};

export default config;

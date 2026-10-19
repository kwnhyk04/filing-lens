// The e2e suite: one `next build` (run it first), served twice against the mock API, no network.
import { defineConfig, devices } from "@playwright/test";

import { API_KEY, LIVE, MOCK, OFFLINE, SESSION_SECRET, STATE, passwordHash } from "./e2e/env.ts";

const env = { API_KEY, SESSION_SECRET, LOGIN_PASSWORD_HASH: passwordHash() };
const next = (base: string, apiUrl: string) => ({
  command: `node node_modules/next/dist/bin/next start -H 127.0.0.1 -p ${new URL(base).port}`,
  url: `${base}/healthz`,
  env: { ...env, API_URL: apiUrl },
  reuseExistingServer: false,
  stdout: "pipe" as const, // the web's JSON log lines, in the run's output
  timeout: 60_000,
});

export default defineConfig({
  testDir: "e2e",
  fullyParallel: true,
  workers: 4, // more ran this PC out of socket buffers (net::ERR_NO_BUFFER_SPACE)
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: { ...devices["Desktop Chrome"], trace: "retain-on-failure" },
  webServer: [
    { command: "node e2e/mock-api.ts", url: `${MOCK}/healthz`, reuseExistingServer: false },
    next(LIVE, MOCK),
    next(OFFLINE, "http://0.0.0.0:1"), // fails at once, like an API that is off
  ],
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/, use: { baseURL: LIVE } },
    {
      name: "live",
      testIgnore: /(offline|lockout)\.spec\.ts/,
      dependencies: ["setup"],
      use: { baseURL: LIVE, storageState: STATE },
    },
    { name: "offline", testMatch: /offline\.spec\.ts/, dependencies: ["setup"], use: { baseURL: OFFLINE, storageState: STATE } },
    // Last: it locks the live server's sign-in for 15 minutes.
    { name: "lockout", testMatch: /lockout\.spec\.ts/, dependencies: ["live", "offline"], use: { baseURL: LIVE } },
  ],
});

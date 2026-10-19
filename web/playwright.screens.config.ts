// `npm run screens` (after `npm run build`): every screen in light, dark and phone width, against the
// mock API, into docs/screenshots/ui. The e2e run never matches e2e/screens.ts.
import { defineConfig } from "@playwright/test";

import { LIVE, STATE } from "./e2e/env.ts";
import base from "./playwright.config.ts";

export default defineConfig({
  ...base,
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/, use: { baseURL: LIVE } },
    { name: "screens", testMatch: /screens\.ts$/, dependencies: ["setup"], use: { baseURL: LIVE, storageState: STATE } },
  ],
});

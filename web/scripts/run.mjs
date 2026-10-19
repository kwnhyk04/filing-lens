// `npm run dev` and `npm start`: next with the web's keys from the repo's .env; a real env var wins.
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { parseEnv } from "node:util";

const WEB_KEYS = ["API_URL", "API_KEY", "SESSION_SECRET", "LOGIN_PASSWORD_HASH", "WEB_PORT"];

/** The child's environment: the inherited one, plus the web's keys from `.env` text it lacks. */
export function webEnv(inherited, dotenv) {
  const file = dotenv === undefined ? {} : parseEnv(dotenv); // literal values: no ${} expansion
  const env = { ...inherited };
  for (const key of WEB_KEYS) if (env[key] === undefined && file[key] !== undefined) env[key] = file[key];
  delete env.ADMIN_API_KEY; // the web holds API_KEY only
  return env;
}

function readDotenv(url) {
  try {
    return readFileSync(url, "utf8");
  } catch (error) {
    if (error.code === "ENOENT") return undefined;
    throw error;
  }
}

if (import.meta.main) {
  const mode = process.argv[2];
  if (mode !== "dev" && mode !== "start") {
    console.error("usage: node scripts/run.mjs dev|start");
    process.exit(2);
  }
  const env = webEnv(process.env, readDotenv(new URL("../../.env", import.meta.url)));
  const next = createRequire(import.meta.url).resolve("next/dist/bin/next");
  const args = [next, mode, "--hostname", "127.0.0.1", "--port", env.WEB_PORT ?? "3100"];
  spawn(process.execPath, args, { env, stdio: "inherit" }).on("exit", (code) => process.exit(code ?? 1));
}

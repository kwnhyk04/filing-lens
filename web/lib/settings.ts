// The web server's settings from env vars, checked at startup; errors name variables, never values.
import { parsePhc } from "./password.ts";

export interface Settings {
  apiUrl: string;
  apiKey: string;
  sessionSecret: string;
  passwordHash: string;
}

export const MIN_SECRET = 32; // verifySession refuses a shorter session secret too

function longEnough(value: string): string | undefined {
  return value.length >= MIN_SECRET ? undefined : `at least ${MIN_SECRET} characters`;
}

export function loadSettings(env: Record<string, string | undefined>): Settings {
  const problems: string[] = [];
  const read = (name: string, check: (value: string) => string | undefined): string => {
    const value = env[name] ?? "";
    const problem = value ? check(value) : "required";
    if (problem) problems.push(`${name}: ${problem}`);
    return value;
  };
  const settings = {
    apiUrl: read("API_URL", (value) =>
      /^https?:\/\/[^/]/.test(value) && URL.canParse(value) ? undefined : "an http(s) URL",
    ),
    apiKey: read("API_KEY", longEnough),
    sessionSecret: read("SESSION_SECRET", longEnough),
    passwordHash: read("LOGIN_PASSWORD_HASH", (value) => {
      try {
        parsePhc(value);
      } catch (error) {
        return (error as Error).message;
      }
    }),
  };
  if (problems.length) throw new Error(`Invalid configuration: ${problems.join("; ")}`);
  return settings;
}

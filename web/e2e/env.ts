// The e2e suite's ports and test-only settings, shared by the config, the mock API and the specs.
import { argon2Sync, randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";

export { SESSION_COOKIE } from "../lib/session.ts";

const port = (name: string, fallback: number) => Number(process.env[name] ?? fallback);
export const MOCK = `http://127.0.0.1:${port("E2E_MOCK_PORT", 4101)}`;
export const LIVE = `http://127.0.0.1:${port("E2E_LIVE_PORT", 3102)}`;
export const OFFLINE = `http://127.0.0.1:${port("E2E_OFFLINE_PORT", 3103)}`;
export const API_KEY = "e2e-mock-api-key-0123456789abcdef";
export const SESSION_SECRET = "e2e-session-secret-0123456789abcdef";
export const PASSWORD = "e2e only, never a real password";
export const STATE = "e2e/.auth/session.json";

/** An argon2id hash of PASSWORD at the web's lowest accepted cost, so the config loads fast. */
export function passwordHash(): string {
  const salt = randomBytes(16);
  const params = { message: PASSWORD, nonce: salt, memory: 19456, passes: 2, parallelism: 1, tagLength: 32 };
  const b64 = (bytes: Buffer) => bytes.toString("base64").replace(/=+$/, "");
  return `$argon2id$v=19$m=19456,t=2,p=1$${b64(salt)}$${b64(argon2Sync("argon2id", params))}`;
}

export interface DemoAnswer {
  id: string;
  question: string;
  answer: { answer: string; citations: unknown[]; refused: boolean; warnings: string[] };
}

export const snapshot = JSON.parse(readFileSync(new URL("../demo/snapshot.json", import.meta.url), "utf8")) as {
  answers: DemoAnswer[];
  companies: { cik: number }[];
  sources: { chunks: { id: string }[]; facts: { id: string }[] };
};

export function question(id: string): string {
  const found = snapshot.answers.find((item) => item.id === id);
  if (!found) throw new Error(`${id} is not in the snapshot`);
  return found.question;
}

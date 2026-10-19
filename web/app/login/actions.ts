"use server";
// Sign-in: the limiter runs before argon2, and a success sets the session cookie.
import { cookies, headers } from "next/headers";
import { redirect } from "next/navigation";

import { safeNext } from "../../lib/guards.ts";
import { log } from "../../lib/log.ts";
import { parsePhc, verifyPassword } from "../../lib/password.ts";
import { config, signInLimiter } from "../../lib/server.ts";
import { SESSION_COOKIE, SESSION_TTL_S, signSession } from "../../lib/session.ts";

export interface SignInState {
  error?: string;
  attempt?: number;
}

/** Locally every client is on this PC, so one bucket; on Vercel, the client IP it sets. */
async function clientKey(): Promise<string> {
  return process.env.VERCEL === "1" ? ((await headers()).get("x-real-ip") ?? "unknown") : "local";
}

export async function signIn(state: SignInState, form: FormData): Promise<SignInState> {
  const key = await clientKey();
  const attempt = (state.attempt ?? 0) + 1; // a new message node each time, so it is announced again
  // Counted before argon2 with no await in between, so parallel attempts cannot all pass.
  const wait = signInLimiter.attempt(key);
  if (wait) {
    log("sign_in_locked", { retry_after_s: wait }, "warn");
    return { error: `Too many failed attempts. Try again in ${Math.ceil(wait / 60)} minutes.`, attempt };
  }
  const password = form.get("password");
  const valid =
    typeof password === "string" &&
    password.length > 0 &&
    password.length <= 1024 &&
    (await verifyPassword(password, parsePhc(config().passwordHash)));
  if (!valid) {
    log("sign_in_failed", {}, "warn");
    return { error: "Wrong password.", attempt };
  }
  signInLimiter.reset(key);
  const token = signSession(config().sessionSecret, Date.now());
  const cookie = { httpOnly: true, secure: true, sameSite: "lax", path: "/", maxAge: SESSION_TTL_S } as const;
  (await cookies()).set(SESSION_COOKIE, token, cookie);
  log("signed_in");
  const next = form.get("next");
  redirect(safeNext(typeof next === "string" ? next : null) ?? "/");
}

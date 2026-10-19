"use client";
import { useActionState } from "react";

import { signIn, type SignInState } from "./actions.ts";

export function SignInForm({ next }: { next: string }) {
  const [state, action, pending] = useActionState<SignInState, FormData>(signIn, {});
  return (
    <form action={action} onSubmit={(event) => pending && event.preventDefault()} className="stack">
      <input type="hidden" name="next" value={next} />
      <label htmlFor="password">Password</label>
      <input
        id="password"
        name="password"
        type="password"
        autoComplete="current-password"
        required
        maxLength={1024}
        aria-invalid={state.error ? true : undefined}
        aria-describedby="password-error"
      />
      <p id="password-error" className="error" data-testid="sign-in-error" aria-live="polite">
        {/* A new node per attempt, so a repeated "Wrong password." is announced again */}
        <span key={state.attempt}>{state.error}</span>
      </p>
      {/* aria-disabled, not disabled: a disabled button would drop the keyboard user's focus */}
      <button type="submit" aria-disabled={pending || undefined}>
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
